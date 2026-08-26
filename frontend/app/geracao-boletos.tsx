// Geração de Boletos (Financeiro > Cobranças) — baseada em frmrelbol4.frm
// (Kontacto) + FrmImpRetBan.frm (Geral). Web-only, mesmo padrão de bancos.tsx.
//
// Unificada numa única tela com 2 abas (2026-07-24, user-directed —
// "todo o processamento de remessa e retorno é através da tela Geração de
// Boletos... pode colocar as 2 telas em uma única tela de Geração de
// Boletos com 2 Abas: Geração/Envio e Importação Retorno"): a tela
// retorno-bancario.tsx foi removida, seu conteúdo virou a aba "Importação
// Retorno" abaixo.
//
// Aba Geração/Envio (ver PENDENCIAS.md > "Boleto em PDF"): filtros + grade
// de títulos + Gerar Remessa (reaproveita os motores CNAB já prontos) +
// Gerar Planilha (Excel) + (2026-08-26) Baixar PDF/Enviar por Email —
// código de barras real, ver backend/services/boleto_pdf_service.py.
//
// Simplificação deliberada: "Gerar Remessa" chama o MESMO endpoint
// genérico já usado em bancos.tsx (todos os títulos pendentes do banco,
// não só os filtrados/visíveis na grade) — os motores CNAB não aceitam
// hoje uma lista específica de títulos, então não há seleção de linha
// nesta tela (ao contrário do legado, que deixa marcar/desmarcar).
//
// Aba Importação Retorno — simplificação deliberada em relação ao legado
// (ver backend/services/cobranca_retorno_service.py): só o fluxo de BAIXA
// (ocorrência 06/09/17 — a ação com impacto financeiro real) vira uma
// grade selecionável linha a linha; confirmações (02/03) viram só uma
// contagem-resumo, não uma lista selecionável — os motores CNAB400
// (Inter/Itaú) não extraem hoje o identificador usado pra achar o título
// nesse caso. Registrado em PENDENCIAS.md. O conteúdo do arquivo é lido
// via seletor de arquivo do sistema operacional (nunca colado à mão) — o
// processamento acontece em segundo plano assim que o arquivo é escolhido.
import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { apiBase, apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

type BancoOpt = { cod: number; codigo: number; descricao: string; carteira: number };
type ContaOpt = { codigo: number; descricao: string; conta_principal_painel: boolean };
type Titulo = {
  drv_codigo: number; cliente_codigo: number; cliente_nome: string | null; duplicata: number;
  dt_emissao: string | null; dt_vencimento: string | null; taxa_bancaria: number; multa_atraso: number;
  multa_dia_atraso: number; valor_total: number; numero_boleto: number | null; registrado: boolean; parcela_info: string;
};
type ItemBaixa = {
  drv_codigo: number | null; numero_boleto: string; ocorrencia: string; cliente_nome: string | null;
  documento: number | string | null; vencimento: string | null; valor_titulo: number | null;
  data_pag: string | null; valor_pago: number; juros: number; desconto: number; ja_baixado: boolean;
  encontrado: boolean;
};
type ResultadoEnvioBoleto = { codigo: number; success: boolean; message: string | null };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function fmtMoeda(v: number) {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtData(iso: string | null) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

export default function GeracaoBoletosScreen() {
  const router = useRouter();
  const { can, isMaster, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Geração de Boletos está disponível apenas no web." testID="geracao-boletos-web-only" />;
  }

  const canAbrirGeracao = can("GERACAO_BOLETOS.ABRIR") || isMaster;
  const canAbrirRetorno = can("RETORNO_BANC.ABRIR") || isMaster;
  const canRemessa = can("GERACAO_BOLETOS.GERAR_REMESSA") || isMaster;
  const canExportar = can("GERACAO_BOLETOS.EXPORTAR") || isMaster;
  const canBaixar = can("RETORNO_BANC.BAIXAR") || isMaster;
  const canPdf = can("GERACAO_BOLETOS.PDF") || isMaster;
  const canEmail = can("GERACAO_BOLETOS.EMAIL") || isMaster;

  const [aba, setAba] = useState<"geracao" | "retorno">(canAbrirGeracao ? "geracao" : "retorno");

  const [conn, setConn] = useState<Connection | null>(null);
  const [bancos, setBancos] = useState<BancoOpt[]>([]);
  const [bancoCod, setBancoCod] = useState<number | null>(null);
  const [contas, setContas] = useState<SelectOption[]>([]);
  const [bancoCodRetorno, setBancoCodRetorno] = useState<number | null>(null);
  const [contaCod, setContaCod] = useState<number | null>(null);

  const [emissaoDe, setEmissaoDe] = useState<string | null>(todayIso());
  const [emissaoAte, setEmissaoAte] = useState<string | null>(todayIso());
  const [vencimentoDe, setVencimentoDe] = useState<string | null>(null);
  const [vencimentoAte, setVencimentoAte] = useState<string | null>(null);
  const [duplicata, setDuplicata] = useState("");
  const [numeroBoleto, setNumeroBoleto] = useState("");
  const [soSemBoleto, setSoSemBoleto] = useState(false);
  const [somenteRegistrados, setSomenteRegistrados] = useState(false);

  // Campo Cliente — padrão global ([GLOBAL], ver CLAUDE.md "Padrão de
  // Campo Cliente"): sempre editável, Enter resolve (1 resultado = direto,
  // 0/2+ abre o modal de busca completo), botão dedicado sempre abre o
  // modal. O filtro real enviado ao backend é sempre um cliente_codigo
  // exato, nunca o texto livre.
  const [clienteSelecionado, setClienteSelecionado] = useState<ClienteRow | null>(null);
  const [clienteQuickTerm, setClienteQuickTerm] = useState("");
  const [clienteQuickLoading, setClienteQuickLoading] = useState(false);
  const [cliSearchOpen, setCliSearchOpen] = useState(false);
  const [cliSearchTerm, setCliSearchTerm] = useState("");
  const [cliSearchResults, setCliSearchResults] = useState<ClienteRow[]>([]);
  const [cliSearchLoading, setCliSearchLoading] = useState(false);

  const [itens, setItens] = useState<Titulo[]>([]);
  const [selecionadosGeracao, setSelecionadosGeracao] = useState<Set<number>>(new Set());
  const [carregando, setCarregando] = useState(false);
  const [remessaSaving, setRemessaSaving] = useState(false);
  const [pdfSaving, setPdfSaving] = useState(false);
  const [emailSaving, setEmailSaving] = useState(false);
  const [resultadosEmail, setResultadosEmail] = useState<ResultadoEnvioBoleto[] | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  // Aba Importação Retorno
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [arquivoNome, setArquivoNome] = useState("");
  const [ultimoConteudoRetorno, setUltimoConteudoRetorno] = useState("");
  const [carregandoRetorno, setCarregandoRetorno] = useState(false);
  const [baixandoRetorno, setBaixandoRetorno] = useState(false);
  const [itensRetorno, setItensRetorno] = useState<ItemBaixa[]>([]);
  const [selecionadosRetorno, setSelecionadosRetorno] = useState<Set<string>>(new Set());
  const [resumoRetorno, setResumoRetorno] = useState<{ confirmados: number; ignorados: number; naoEncontrados: string[] } | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      try {
        const jb = await apiGet(c, "/api/bancos");
        const ativos: BancoOpt[] = (jb?.items || []).filter((b: any) => b.situacao === "A");
        setBancos(ativos);
        if (ativos.length > 0) {
          setBancoCod(ativos[0].cod);
          setBancoCodRetorno(ativos[0].cod);
        }
      } catch { setBancos([]); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // Contas visíveis no campo "Conta" (aba Importação Retorno) respeitam o
  // crivo de "Contas x Funcionário" (ver conta_func_service.py) — cada
  // funcionário só vê as contas explicitamente vinculadas a ele; master
  // sempre vê todas. Efeito separado (não no mount acima) porque
  // isMaster/usuarioCodigo do usePermissions() só ficam prontos depois de
  // um carregamento assíncrono próprio — refaz a busca quando mudarem.
  useEffect(() => {
    if (!conn) return;
    (async () => {
      try {
        const jc = await apiGet(conn, "/api/conta-funcionario/visiveis", {
          funcionario: usuarioCodigo ?? undefined,
          master: isMaster,
        });
        const listaContas: ContaOpt[] = jc?.items || [];
        setContas(listaContas.map((x) => ({ value: x.codigo, label: x.descricao })));
        const padrao = listaContas.find((x) => x.conta_principal_painel);
        setContaCod(padrao ? padrao.codigo : null);
      } catch { setContas([]); }
    })();
  }, [conn, isMaster, usuarioCodigo]);

  const bancoOptions: SelectOption[] = useMemo(
    () => bancos.map((b) => ({ value: b.cod, label: b.descricao, sub: `${b.codigo} · carteira ${b.carteira}` })),
    [bancos]
  );

  // Busca ao vivo dentro do modal (debounce), mesmo padrão de
  // relatorio-margem-lucro.tsx — independente da resolução por Enter.
  useEffect(() => {
    if (!cliSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setCliSearchLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term: cliSearchTerm });
        setCliSearchResults(j?.items || []);
      } catch {
        setCliSearchResults([]);
      } finally {
        setCliSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [cliSearchTerm, cliSearchOpen, conn]);

  const handlePickCliente = (c: ClienteRow) => {
    setClienteSelecionado(c);
    setClienteQuickTerm(c.nome);
    setCliSearchOpen(false);
  };

  const handleClienteQuickChange = (v: string) => {
    setClienteQuickTerm(v);
    if (clienteSelecionado) setClienteSelecionado(null);
  };

  // Enter é o único gatilho de busca — digitar sozinho não dispara nada.
  // 1 resultado carrega o cliente direto; 0 ou 2+ abrem o modal de busca
  // completo, mesmo comportamento de ClienteSection (Pedido/O.S.).
  const resolveClienteQuickTerm = async () => {
    const t = clienteQuickTerm.trim();
    if (!t || !conn) return;
    setClienteQuickLoading(true);
    try {
      const j = await apiGet(conn, "/api/clientes/find/search", { term: t });
      const results: ClienteRow[] = j?.items || [];
      if (results.length === 1) {
        handlePickCliente(results[0]);
      } else {
        setCliSearchTerm(t);
        setCliSearchResults([]);
        setCliSearchOpen(true);
      }
    } catch {
      // silencioso — usuário pode tentar de novo ou usar o botão de busca
    } finally {
      setClienteQuickLoading(false);
    }
  };

  const selecionar = async () => {
    if (!conn || !bancoCod) { fb.showWarning("Selecione um banco."); return; }
    setCarregando(true);
    try {
      const j = await apiSend(conn, `/api/geracao-boletos/${bancoCod}/titulos`, "POST", {
        servidor: conn.servidor, banco: conn.banco,
        emissao_de: emissaoDe || undefined, emissao_ate: emissaoAte || undefined,
        vencimento_de: vencimentoDe || undefined, vencimento_ate: vencimentoAte || undefined,
        duplicata: duplicata ? Number(duplicata) : undefined,
        numero_boleto: numeroBoleto ? Number(numeroBoleto) : undefined,
        cliente_codigo: clienteSelecionado?.codigo,
        so_sem_boleto: soSemBoleto, somente_registrados: somenteRegistrados,
      });
      if (j?.success) {
        const lista: Titulo[] = j.items || [];
        setItens(lista);
        setSelecionadosGeracao(new Set(lista.map((it) => it.drv_codigo)));
        if (lista.length === 0) fb.showWarning("Nenhum registro encontrado.");
      } else {
        setItens([]);
        setSelecionadosGeracao(new Set());
        fb.showError(friendlyApiError(j, "Falha ao buscar títulos."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao buscar títulos."));
    } finally {
      setCarregando(false);
    }
  };

  const toggleItemGeracao = (drv: number) => {
    setSelecionadosGeracao((prev) => {
      const next = new Set(prev);
      if (next.has(drv)) next.delete(drv); else next.add(drv);
      return next;
    });
  };
  const marcarTodosGeracao = () => setSelecionadosGeracao(new Set(itens.map((it) => it.drv_codigo)));
  const desmarcarTodosGeracao = () => setSelecionadosGeracao(new Set());

  const gerarRemessa = async () => {
    if (!conn || !bancoCod) return;
    if (itens.length > 0 && selecionadosGeracao.size === 0) {
      fb.showWarning("Selecione ao menos um título.");
      return;
    }
    setRemessaSaving(true);
    try {
      // Sem grade carregada (usuário foi direto em "Gerar Remessa" sem
      // clicar "Selecionar" antes) mantém o comportamento antigo: TODOS os
      // títulos pendentes do banco. Com grade carregada, só os selecionados
      // (padrão: todos marcados) entram na remessa.
      const titulosSelecionados = itens.length > 0 ? Array.from(selecionadosGeracao) : undefined;
      const j = await apiSend(conn, `/api/bancos/${bancoCod}/remessa`, "POST", {
        ...auditCtx, servidor: conn.servidor, banco: conn.banco, titulos: titulosSelecionados,
      });
      if (j?.success) {
        const blob = new Blob([j.conteudo], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = j.nome_arquivo; a.click();
        URL.revokeObjectURL(url);
        fb.showSuccess(`Remessa nº ${j.num_remessa} gerada com ${j.qtd_titulos} título(s) — arquivo "${j.nome_arquivo}" baixado.`, undefined, 5000);
        selecionar();
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gerar remessa."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gerar remessa."));
    } finally {
      setRemessaSaving(false);
    }
  };

  const gerarPlanilha = () => {
    if (itens.length === 0) { fb.showWarning("Nenhum título na grade para exportar."); return; }
    const linhas = itens.map((it) => ({
      Cliente: it.cliente_nome || "", Duplicata: it.duplicata, Emissão: fmtData(it.dt_emissao),
      Vencimento: fmtData(it.dt_vencimento), "Taxa Bancária": it.taxa_bancaria, "Multa Atraso": it.multa_atraso,
      "Multa Dia Atraso": it.multa_dia_atraso, "Valor Total": it.valor_total, "Nº Boleto": it.numero_boleto || "",
      Registrado: it.registrado ? "Sim" : "Não", Parcela: it.parcela_info,
    }));
    exportSheetsToXlsx(`boletos_${new Date().toISOString().slice(0, 10)}.xlsx`, [{ name: "Boletos", rows: linhas }]);
  };

  const titulosSelecionadosParaAcao = (): number[] | null => {
    if (itens.length === 0) { fb.showWarning("Selecione os títulos na grade primeiro (clique em \"Selecionar\")."); return null; }
    const sel = Array.from(selecionadosGeracao);
    if (sel.length === 0) { fb.showWarning("Selecione ao menos um título."); return null; }
    return sel;
  };

  // Gera o PDF dos boletos marcados na grade — registra cada título no
  // banco escolhido (idempotente, ver boleto_pdf_service.py) e baixa um
  // único PDF multi-página com o código de barras real.
  const baixarPdf = async () => {
    if (!conn || !bancoCod) return;
    const titulos = titulosSelecionadosParaAcao();
    if (!titulos) return;
    setPdfSaving(true);
    try {
      const resp = await fetch(`${apiBase(conn)}/api/geracao-boletos/${bancoCod}/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...auditCtx, servidor: conn.servidor, banco: conn.banco, titulos }),
      });
      const contentType = resp.headers.get("content-type") || "";
      if (!resp.ok || !contentType.includes("application/pdf")) {
        const j = await resp.json().catch(() => null);
        fb.showError(friendlyApiError(j, "Falha ao gerar o PDF do boleto."));
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "boletos.pdf"; a.click();
      URL.revokeObjectURL(url);
      fb.showSuccess(`PDF gerado com ${titulos.length} boleto(s).`);
      selecionar();
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gerar o PDF do boleto."));
    } finally {
      setPdfSaving(false);
    }
  };

  // Envia por e-mail (com o boleto em PDF anexado) os títulos marcados —
  // pra cada um: registra o título no banco (mesma gravação do PDF),
  // resolve o e-mail do cliente e dispara via email_cobranca_service.
  const executarEnvioEmail = async (titulos: number[]) => {
    if (!conn || !bancoCod) return;
    setEmailSaving(true);
    setResultadosEmail(null);
    try {
      const j = await apiSend(conn, `/api/geracao-boletos/${bancoCod}/enviar-email`, "POST", {
        ...auditCtx, servidor: conn.servidor, banco: conn.banco, titulos,
      });
      if (j?.success) {
        const resultados: ResultadoEnvioBoleto[] = j.resultados || [];
        setResultadosEmail(resultados);
        const sucessos = resultados.filter((r) => r.success).length;
        fb.showSuccess(`${sucessos} de ${resultados.length} boleto(s) enviado(s) com sucesso.`, undefined, 5000);
        selecionar();
      } else {
        fb.showError(friendlyApiError(j, "Falha ao enviar boletos por e-mail."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao enviar boletos por e-mail."));
    } finally {
      setEmailSaving(false);
    }
  };

  const enviarEmailBoletos = () => {
    const titulos = titulosSelecionadosParaAcao();
    if (!titulos) return;
    fb.showConfirm(
      `Enviar o boleto por e-mail para ${titulos.length} cliente(s) selecionado(s)?`,
      () => executarEnvioEmail(titulos),
      { confirmText: "Enviar", cancelText: "Cancelar" }
    );
  };

  // --- Aba Importação Retorno ---

  const limparResultadoRetorno = () => { setItensRetorno([]); setSelecionadosRetorno(new Set()); setResumoRetorno(null); };

  const processarConteudoRetorno = async (conteudo: string) => {
    if (!conn || !bancoCodRetorno) { fb.showWarning("Selecione um banco."); return; }
    if (!conteudo.trim()) { fb.showWarning("O arquivo selecionado está vazio."); return; }
    setCarregandoRetorno(true);
    try {
      const j = await apiSend(conn, `/api/bancos/${bancoCodRetorno}/retorno/preview`, "POST", { servidor: conn.servidor, banco: conn.banco, conteudo });
      if (j?.success) {
        // Lista pra revisão inclui TANTO os títulos encontrados (selecionáveis
        // pra baixa, todos marcados por padrão) QUANTO os não encontrados no
        // arquivo (só pra conferência — sem título local pra atualizar, não
        // selecionáveis) — pedido explícito do usuário (2026-07-24): "tem que
        // listar os títulos... não só contar".
        const encontrados: ItemBaixa[] = j.itens_baixa || [];
        const naoEncontrados: ItemBaixa[] = j.itens_nao_encontrados || [];
        const lista = [...encontrados, ...naoEncontrados];
        setItensRetorno(lista);
        setSelecionadosRetorno(new Set(encontrados.filter((i) => !i.ja_baixado).map((i) => i.numero_boleto)));
        setResumoRetorno({ confirmados: j.confirmados || 0, ignorados: j.ignorados || 0, naoEncontrados: j.nao_encontrados || [] });
        if (lista.length === 0 && (j.confirmados || 0) === 0) {
          fb.showWarning("Nenhum título reconhecido nesse arquivo para este banco.");
        }
      } else {
        limparResultadoRetorno();
        fb.showError(friendlyApiError(j, "Falha ao ler o arquivo de retorno."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao ler o arquivo de retorno."));
    } finally {
      setCarregandoRetorno(false);
    }
  };

  const abrirSeletorArquivo = () => {
    if (!bancoCodRetorno) { fb.showWarning("Selecione um banco."); return; }
    fileInputRef.current?.click();
  };

  const handleArquivoSelecionado = (e: any) => {
    const file: File | undefined = e.target?.files?.[0];
    e.target.value = "";
    if (!file) return;
    setArquivoNome(file.name);
    limparResultadoRetorno();
    const reader = new FileReader();
    reader.onload = () => {
      const texto = String(reader.result || "");
      setUltimoConteudoRetorno(texto);
      processarConteudoRetorno(texto);
    };
    reader.onerror = () => fb.showError("Falha ao ler o arquivo selecionado.");
    reader.readAsText(file);
  };

  const toggleItemRetorno = (numeroBoleto: string) => {
    setSelecionadosRetorno((prev) => {
      const next = new Set(prev);
      if (next.has(numeroBoleto)) next.delete(numeroBoleto); else next.add(numeroBoleto);
      return next;
    });
  };
  const marcarTodosRetorno = () => setSelecionadosRetorno(new Set(itensRetorno.filter((i) => i.encontrado && !i.ja_baixado).map((i) => i.numero_boleto)));
  const desmarcarTodosRetorno = () => setSelecionadosRetorno(new Set());

  const baixarSelecionadosRetorno = async () => {
    if (!conn || !bancoCodRetorno) return;
    const selItens = itensRetorno.filter((i) => i.encontrado && selecionadosRetorno.has(i.numero_boleto));
    if (selItens.length === 0) { fb.showWarning("Selecione ao menos um título."); return; }
    setBaixandoRetorno(true);
    try {
      const j = await apiSend(conn, `/api/bancos/${bancoCodRetorno}/retorno/aplicar`, "POST", {
        ...auditCtx, servidor: conn.servidor, banco: conn.banco, itens: selItens, conta: contaCod || undefined,
      });
      if (j?.success) {
        fb.showSuccess(`${j.baixados} título(s) baixado(s)${j.ja_baixados ? ` (${j.ja_baixados} já estava(m) baixado(s))` : ""}.`, undefined, 5000);
        if (ultimoConteudoRetorno) await processarConteudoRetorno(ultimoConteudoRetorno);
      } else {
        fb.showError(friendlyApiError(j, "Falha ao baixar títulos."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao baixar títulos."));
    } finally {
      setBaixandoRetorno(false);
    }
  };

  if (!canAbrirGeracao && !canAbrirRetorno) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar esta tela." testID="geracao-boletos-locked" />;
  }

  const mostrarAbas = canAbrirGeracao && canAbrirRetorno;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="geracao-boletos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Geração de Boletos</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {mostrarAbas ? (
            <View style={styles.tabBar}>
              <Pressable onPress={() => setAba("geracao")} style={[styles.tabBtn, aba === "geracao" && styles.tabBtnSel]} testID="geracao-boletos-tab-geracao">
                <Ionicons name="document-text-outline" size={16} color={aba === "geracao" ? colors.onBrandPrimary : colors.brandPrimary} />
                <Text style={[styles.tabBtnText, aba === "geracao" && styles.tabBtnTextSel]}>Geração/Envio</Text>
              </Pressable>
              <Pressable onPress={() => setAba("retorno")} style={[styles.tabBtn, aba === "retorno" && styles.tabBtnSel]} testID="geracao-boletos-tab-retorno">
                <Ionicons name="cloud-upload-outline" size={16} color={aba === "retorno" ? colors.onBrandPrimary : colors.brandPrimary} />
                <Text style={[styles.tabBtnText, aba === "retorno" && styles.tabBtnTextSel]}>Importação Retorno</Text>
              </Pressable>
            </View>
          ) : null}

          {aba === "geracao" && canAbrirGeracao ? (
            <>
              <View style={[styles.filters, styles.filtersWeb]}>
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Banco *</Text>
                    <SelectField value={bancoCod} onChange={(v) => setBancoCod(v as number | null)} options={bancoOptions} placeholder="Selecione o banco…" compactWeb testID="geracao-boletos-banco" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Duplicata</Text>
                    <TextInput value={duplicata} onChangeText={(v) => setDuplicata(v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="geracao-boletos-duplicata" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Nº do Boleto</Text>
                    <TextInput value={numeroBoleto} onChangeText={(v) => setNumeroBoleto(v.replace(/\D/g, ""))} keyboardType="number-pad" style={styles.input} testID="geracao-boletos-numero" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Cliente</Text>
                    <View style={styles.clienteBox}>
                      <TextInput
                        value={clienteQuickTerm}
                        onChangeText={handleClienteQuickChange}
                        onSubmitEditing={resolveClienteQuickTerm}
                        returnKeyType="search"
                        selectTextOnFocus
                        style={styles.clienteInput}
                        placeholder="Nome, código, CNPJ/CPF ou telefone… (Enter busca)"
                        placeholderTextColor={colors.muted}
                        testID="geracao-boletos-cliente"
                        autoComplete="new-password"
                        autoCorrect={false}
                        textContentType="none"
                        importantForAutofill="no"
                      />
                      {clienteQuickLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
                      {clienteQuickTerm ? (
                        <Pressable
                          onPress={() => { setClienteQuickTerm(""); setClienteSelecionado(null); }}
                          hitSlop={8}
                          testID="geracao-boletos-cliente-limpar"
                        >
                          <Ionicons name="close-circle" size={18} color={colors.muted} />
                        </Pressable>
                      ) : null}
                      <IconButtonWithTooltip
                        icon="search-outline"
                        label="Buscar cliente"
                        onPress={() => { setCliSearchTerm(clienteQuickTerm); setCliSearchResults([]); setCliSearchOpen(true); }}
                        testID="geracao-boletos-cliente-buscar"
                      />
                    </View>
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Emissão de</Text>
                    <WebDateField value={emissaoDe} onChange={(v) => { setEmissaoDe(v || null); if (v) setEmissaoAte(v); }} testID="geracao-boletos-emissao-de" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Emissão até</Text>
                    <WebDateField value={emissaoAte} onChange={(v) => setEmissaoAte(v || null)} testID="geracao-boletos-emissao-ate" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Vencimento de</Text>
                    <WebDateField value={vencimentoDe} onChange={(v) => { setVencimentoDe(v || null); if (v) setVencimentoAte(v); }} testID="geracao-boletos-vencimento-de" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Vencimento até</Text>
                    <WebDateField value={vencimentoAte} onChange={(v) => setVencimentoAte(v || null)} testID="geracao-boletos-vencimento-ate" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <Pressable onPress={() => setSoSemBoleto((v) => !v)} style={styles.checkboxRow} testID="geracao-boletos-so-sem-boleto">
                    <Ionicons name={soSemBoleto ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.checkboxLabel}>Só duplicatas sem boleto</Text>
                  </Pressable>
                  <Pressable onPress={() => setSomenteRegistrados((v) => !v)} style={styles.checkboxRow} testID="geracao-boletos-somente-registrados">
                    <Ionicons name={somenteRegistrados ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.checkboxLabel}>Somente registrados</Text>
                  </Pressable>
                </View>
                <View style={styles.rowFields}>
                  <Pressable onPress={selecionar} disabled={carregando} style={({ pressed }) => [styles.primaryBtn, (pressed || carregando) && { opacity: 0.8 }]} testID="geracao-boletos-selecionar">
                    {carregando ? (
                      <><ActivityIndicator size="small" color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Buscando…</Text></>
                    ) : (
                      <><Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Selecionar</Text></>
                    )}
                  </Pressable>
                  {canRemessa ? (
                    <Pressable onPress={gerarRemessa} disabled={remessaSaving || !bancoCod} style={({ pressed }) => [styles.secondaryBtn, (pressed || remessaSaving) && { opacity: 0.8 }]} testID="geracao-boletos-gerar-remessa">
                      {remessaSaving ? (
                        <><ActivityIndicator size="small" color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Gerando…</Text></>
                      ) : (
                        <><Ionicons name="document-text-outline" size={16} color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Gerar Remessa</Text></>
                      )}
                    </Pressable>
                  ) : null}
                  {canExportar ? (
                    <Pressable onPress={gerarPlanilha} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]} testID="geracao-boletos-gerar-planilha">
                      <Ionicons name="grid-outline" size={16} color={colors.brandPrimary} />
                      <Text style={styles.secondaryBtnText}>Gerar Planilha</Text>
                    </Pressable>
                  ) : null}
                  {canPdf ? (
                    <Pressable onPress={baixarPdf} disabled={pdfSaving || !bancoCod} style={({ pressed }) => [styles.secondaryBtn, (pressed || pdfSaving) && { opacity: 0.8 }]} testID="geracao-boletos-baixar-pdf">
                      {pdfSaving ? (
                        <><ActivityIndicator size="small" color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Gerando PDF…</Text></>
                      ) : (
                        <><Ionicons name="document-outline" size={16} color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Baixar PDF</Text></>
                      )}
                    </Pressable>
                  ) : null}
                  {canEmail ? (
                    <Pressable onPress={enviarEmailBoletos} disabled={emailSaving || !bancoCod} style={({ pressed }) => [styles.secondaryBtn, (pressed || emailSaving) && { opacity: 0.8 }]} testID="geracao-boletos-enviar-email">
                      {emailSaving ? (
                        <><ActivityIndicator size="small" color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Enviando…</Text></>
                      ) : (
                        <><Ionicons name="mail-outline" size={16} color={colors.brandPrimary} /><Text style={styles.secondaryBtnText}>Enviar por Email</Text></>
                      )}
                    </Pressable>
                  ) : null}
                </View>
              </View>

              {resultadosEmail && resultadosEmail.length > 0 ? (
                <View style={styles.resumoCard}>
                  {resultadosEmail.map((r) => (
                    <Text key={r.codigo} style={[styles.resumoTexto, !r.success && { color: colors.error }]}>
                      {r.success ? "✓" : "✗"} Título #{r.codigo}: {r.message || (r.success ? "Enviado com sucesso" : "Falha ao enviar")}
                    </Text>
                  ))}
                </View>
              ) : null}

              {itens.length > 0 ? (
                <View style={styles.gridCard}>
                  <Text style={styles.gridTitle}>Boletos que Serão Impressos… ({itens.length}) — {selecionadosGeracao.size} selecionado(s)</Text>
                  <View style={styles.rowFields}>
                    <Pressable onPress={marcarTodosGeracao} style={styles.secondaryBtn} testID="geracao-boletos-marcar-todos">
                      <Text style={styles.secondaryBtnText}>Marcar Todos</Text>
                    </Pressable>
                    <Pressable onPress={desmarcarTodosGeracao} style={styles.secondaryBtn} testID="geracao-boletos-desmarcar-todos">
                      <Text style={styles.secondaryBtnText}>Desmarcar Todos</Text>
                    </Pressable>
                  </View>
                  <View style={styles.gridHeaderRow}>
                    <Text style={[styles.gridHeaderCell, { width: 32 }]} />
                    <Text style={[styles.gridHeaderCell, { flex: 1.4 }]}>Cliente</Text>
                    <Text style={[styles.gridHeaderCell, { width: 80 }]}>Duplicata</Text>
                    <Text style={[styles.gridHeaderCell, { width: 85 }]}>Emissão</Text>
                    <Text style={[styles.gridHeaderCell, { width: 85 }]}>Vencimento</Text>
                    <Text style={[styles.gridHeaderCell, { width: 80 }]}>Taxa Banc.</Text>
                    <Text style={[styles.gridHeaderCell, { width: 80 }]}>Multa</Text>
                    <Text style={[styles.gridHeaderCell, { width: 90 }]}>Valor Total</Text>
                    <Text style={[styles.gridHeaderCell, { width: 80 }]}>Nº Boleto</Text>
                    <Text style={[styles.gridHeaderCell, { width: 70 }]}>Parcela</Text>
                  </View>
                  {itens.map((it) => (
                    <Pressable key={it.drv_codigo} onPress={() => toggleItemGeracao(it.drv_codigo)} style={styles.gridRow}>
                      <View style={{ width: 32, alignItems: "center" }}>
                        <Ionicons
                          name={selecionadosGeracao.has(it.drv_codigo) ? "checkbox" : "square-outline"}
                          size={18}
                          color={colors.brandPrimary}
                        />
                      </View>
                      <Text style={[styles.gridCell, { flex: 1.4 }]} numberOfLines={1}>{it.cliente_nome || "—"}</Text>
                      <Text style={[styles.gridCell, { width: 80 }]}>{it.duplicata}</Text>
                      <Text style={[styles.gridCell, { width: 85 }]}>{fmtData(it.dt_emissao)}</Text>
                      <Text style={[styles.gridCell, { width: 85 }]}>{fmtData(it.dt_vencimento)}</Text>
                      <Text style={[styles.gridCell, { width: 80 }]}>{fmtMoeda(it.taxa_bancaria)}</Text>
                      <Text style={[styles.gridCell, { width: 80 }]}>{fmtMoeda(it.multa_atraso + it.multa_dia_atraso)}</Text>
                      <Text style={[styles.gridCell, { width: 90 }]}>{fmtMoeda(it.valor_total)}</Text>
                      <Text style={[styles.gridCell, { width: 80 }]}>{it.numero_boleto || "—"}</Text>
                      <Text style={[styles.gridCell, { width: 70 }]}>{it.parcela_info}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </>
          ) : null}

          {aba === "retorno" && canAbrirRetorno ? (
            <>
              <View style={[styles.filters, styles.filtersWeb]}>
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Banco *</Text>
                    <SelectField value={bancoCodRetorno} onChange={(v) => { setBancoCodRetorno(v as number | null); limparResultadoRetorno(); }} options={bancoOptions} placeholder="Selecione o banco…" compactWeb testID="retorno-banco" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Conta (opcional, p/ baixa)</Text>
                    <SelectField value={contaCod} onChange={(v) => setContaCod(v as number | null)} options={contas} placeholder="Selecione a conta…" compactWeb allowClear testID="retorno-conta" />
                    {contas.length === 0 && !isMaster ? (
                      <Text style={styles.hintText}>Nenhuma conta liberada para você — peça a um administrador para configurar em "Contas x Funcionário".</Text>
                    ) : null}
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <Pressable
                    onPress={abrirSeletorArquivo}
                    disabled={carregandoRetorno}
                    style={({ pressed }) => [styles.primaryBtn, (pressed || carregandoRetorno) && { opacity: 0.8 }]}
                    testID="retorno-selecionar-arquivo"
                  >
                    {carregandoRetorno ? (
                      <><ActivityIndicator size="small" color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Lendo…</Text></>
                    ) : (
                      <><Ionicons name="folder-open-outline" size={16} color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Selecionar Arquivo</Text></>
                    )}
                  </Pressable>
                  {arquivoNome ? <Text style={styles.arquivoNomeText}>Arquivo: {arquivoNome}</Text> : null}
                </View>
                {/* eslint-disable-next-line react/no-unknown-property */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.ret,.rem,.cnab,.dat"
                  style={{ display: "none" }}
                  onChange={handleArquivoSelecionado}
                  data-testid="retorno-arquivo-input"
                />
              </View>

              {resumoRetorno ? (
                <View style={styles.resumoCard}>
                  <Text style={styles.resumoTexto}>
                    {resumoRetorno.confirmados} confirmação(ões) · {itensRetorno.filter((i) => i.encontrado).length} título(s) p/ baixa · {resumoRetorno.ignorados} linha(s) ignorada(s)
                    {resumoRetorno.naoEncontrados.length ? ` · ${resumoRetorno.naoEncontrados.length} não encontrado(s) — listado(s) abaixo` : ""}
                  </Text>
                </View>
              ) : null}

              {itensRetorno.length > 0 ? (
                <View style={styles.gridCard}>
                  <View style={styles.rowFields}>
                    <Pressable onPress={marcarTodosRetorno} style={styles.secondaryBtn} testID="retorno-marcar-todos">
                      <Text style={styles.secondaryBtnText}>Marcar Todos</Text>
                    </Pressable>
                    <Pressable onPress={desmarcarTodosRetorno} style={styles.secondaryBtn} testID="retorno-desmarcar-todos">
                      <Text style={styles.secondaryBtnText}>Desmarcar Todos</Text>
                    </Pressable>
                    {canBaixar ? (
                      <Pressable
                        onPress={baixarSelecionadosRetorno}
                        disabled={baixandoRetorno}
                        style={({ pressed }) => [styles.primaryBtn, (pressed || baixandoRetorno) && { opacity: 0.8 }]}
                        testID="retorno-baixar-selecionados"
                      >
                        {baixandoRetorno ? (
                          <><ActivityIndicator size="small" color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Baixando…</Text></>
                        ) : (
                          <><Ionicons name="cash-outline" size={16} color={colors.onBrandPrimary} /><Text style={styles.primaryBtnText}>Baixar Títulos Selecionados</Text></>
                        )}
                      </Pressable>
                    ) : null}
                  </View>
                  <View style={styles.gridHeaderRow}>
                    <Text style={[styles.gridHeaderCell, { width: 32 }]} />
                    <Text style={[styles.gridHeaderCell, { flex: 1.4 }]}>Cliente</Text>
                    <Text style={[styles.gridHeaderCell, { width: 90 }]}>Boleto</Text>
                    <Text style={[styles.gridHeaderCell, { width: 90 }]}>Vencimento</Text>
                    <Text style={[styles.gridHeaderCell, { width: 100 }]}>Valor Título</Text>
                    <Text style={[styles.gridHeaderCell, { width: 90 }]}>Data Pag.</Text>
                    <Text style={[styles.gridHeaderCell, { width: 90 }]}>Acréscimo(s)</Text>
                    <Text style={[styles.gridHeaderCell, { width: 100 }]}>Valor Pago</Text>
                    <Text style={[styles.gridHeaderCell, { width: 100 }]}>Documento</Text>
                  </View>
                  {itensRetorno.map((it, idx) => {
                    const bloqueado = it.ja_baixado || !it.encontrado;
                    return (
                      <Pressable
                        key={`${it.numero_boleto}-${idx}`}
                        onPress={() => !bloqueado && toggleItemRetorno(it.numero_boleto)}
                        style={[styles.gridRow, bloqueado && styles.gridRowBaixado]}
                      >
                        <View style={{ width: 32, alignItems: "center" }}>
                          <Ionicons
                            name={selecionadosRetorno.has(it.numero_boleto) ? "checkbox" : "square-outline"}
                            size={18}
                            color={bloqueado ? colors.muted : colors.brandPrimary}
                          />
                        </View>
                        <Text style={[styles.gridCell, { flex: 1.4 }]} numberOfLines={1}>
                          {it.cliente_nome || "—"}
                          {it.ja_baixado ? " (já baixado)" : ""}
                          {!it.encontrado ? " (não encontrado)" : ""}
                        </Text>
                        <Text style={[styles.gridCell, { width: 90 }]}>{it.numero_boleto}</Text>
                        <Text style={[styles.gridCell, { width: 90 }]}>{fmtData(it.vencimento)}</Text>
                        <Text style={[styles.gridCell, { width: 100 }]}>{it.valor_titulo != null ? fmtMoeda(it.valor_titulo) : "—"}</Text>
                        <Text style={[styles.gridCell, { width: 90 }]}>{fmtData(it.data_pag)}</Text>
                        <Text style={[styles.gridCell, { width: 90 }]}>{fmtMoeda(it.juros)}</Text>
                        <Text style={[styles.gridCell, { width: 100 }]}>{fmtMoeda(it.valor_pago)}</Text>
                        <Text style={[styles.gridCell, { width: 100 }]} numberOfLines={1}>{it.documento ?? ""}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : null}
            </>
          ) : null}
        </View>
      </ScrollView>

      <ClientSearchModal
        visible={cliSearchOpen}
        onClose={() => setCliSearchOpen(false)}
        term={cliSearchTerm}
        setTerm={setCliSearchTerm}
        loading={cliSearchLoading}
        results={cliSearchResults}
        onPick={handlePickCliente}
        onCreate={() => setCliSearchOpen(false)}
      />

      <AppModal visible={ajudaOpen} transparent animationType="fade" onRequestClose={() => setAjudaOpen(false)}>
        <Pressable style={styles.helpBg} onPress={() => setAjudaOpen(false)}>
          <Pressable style={styles.helpCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.helpHeader}>
              <Text style={styles.helpTitle}>Ajuda — Geração de Boletos</Text>
              <Pressable onPress={() => setAjudaOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Selecionar{"\n"}</Text>
              Busca os títulos em aberto do banco escolhido, aplicando os filtros de data/duplicata/cliente/nº do boleto.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Gerar Remessa{"\n"}</Text>
              Gera e baixa o arquivo de remessa (CNAB) com os títulos marcados na grade (todos vêm marcados por padrão ao clicar "Selecionar" — use Marcar/Desmarcar Todos ou a caixinha de cada linha pra ajustar). Se "Gerar Remessa" for clicado sem antes buscar a grade, gera para TODOS os títulos em aberto ainda não enviados deste banco.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Gerar Planilha{"\n"}</Text>
              Exporta em Excel os títulos atualmente exibidos na grade (já filtrados).
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Taxa Bancária / Multa{"\n"}</Text>
              Valores estimados a partir da configuração do banco (tarifa de cobrança, % de multa e mora) — só informativos nesta tela, não emitem boleto.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Baixar PDF{"\n"}</Text>
              Gera um PDF com o boleto (código de barras e linha digitável reais, layout padrão de todos os bancos) dos títulos marcados na grade — se algum ainda não tinha sido registrado no banco escolhido, isso acontece automaticamente agora, do mesmo jeito que "Gerar Remessa" já faz.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Geração/Envio — Enviar por Email{"\n"}</Text>
              Envia o boleto em PDF por e-mail pra cada cliente selecionado na grade, usando o e-mail de cobrança cadastrado no cliente. Sem e-mail cadastrado, o título aparece na lista de resultado com "Sem e-mail cadastrado" e não é enviado.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Importação Retorno — Selecionar Arquivo{"\n"}</Text>
              Escolha o banco e clique em "Selecionar Arquivo" para abrir o explorador de arquivos do computador — assim que o arquivo de retorno é escolhido, o sistema lê e processa tudo automaticamente, sem precisar colar nenhum texto.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Importação Retorno — Confirmações vs. Baixas{"\n"}</Text>
              O resumo mostra quantos títulos foram só "confirmados" pelo banco (recebidos, ainda não pagos) — esses não precisam de nenhuma ação. Só os títulos com pagamento (baixa) aparecem na grade abaixo, já marcados por padrão, prontos para conferência.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Importação Retorno — "Não encontrado"{"\n"}</Text>
              Títulos do arquivo que o sistema não conseguiu casar com nenhum boleto cadastrado aqui também aparecem na grade, esmaecidos e sem caixa de seleção — servem só para conferência (ex.: número de boleto digitado errado, banco/conta diferente do cadastrado). Não têm como ser baixados até o motivo ser corrigido.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Importação Retorno — Baixar Títulos Selecionados{"\n"}</Text>
              Marca os títulos selecionados como pagos (situação "PG"), gravando data e valor pago. Títulos já baixados antes aparecem esmaecidos e não podem ser selecionados de novo.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Aba Importação Retorno — Conta{"\n"}</Text>
              Opcional — se selecionada, grava em qual conta de caixa/banco o valor recebido entrou. Já vem pré-selecionada com a conta marcada como padrão do painel, se houver. A lista só mostra as contas liberadas para o seu usuário em "Financeiro {'>'} Fluxo de Caixa {'>'} Contas x Funcionário" — sem nenhuma conta liberada, a lista aparece vazia.
            </Text>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  tabBar: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  tabBtnTextSel: { color: colors.onBrandPrimary },
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  colFlex: { flex: 1, minWidth: 200 },
  clienteBox: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, backgroundColor: colors.surface,
  },
  clienteInput: { flex: 1, paddingVertical: 8, fontSize: 13, color: colors.onSurface },
  colNarrow: { width: 140 },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "600" },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  checkboxRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 6 },
  checkboxLabel: { fontSize: 13, color: colors.onSurface },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  arquivoNomeText: { fontSize: 12, color: colors.muted, fontStyle: "italic" },
  resumoCard: {
    marginTop: spacing.sm, padding: spacing.sm, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  resumoTexto: { fontSize: 12, color: colors.onSurfaceSecondary },
  gridCard: {
    marginTop: spacing.md, padding: spacing.sm, borderRadius: radius.md,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, gap: 4,
  },
  gridTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginBottom: 4 },
  gridHeaderRow: { flexDirection: "row", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridHeaderCell: { fontSize: 11, fontWeight: "700", color: colors.muted },
  gridRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowBaixado: { opacity: 0.5 },
  hintText: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  gridCell: { fontSize: 12, color: colors.onSurface, paddingRight: 4 },
  helpBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center" },
  helpCard: { width: "100%", maxWidth: 560, maxHeight: "80%", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg },
  helpHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  helpTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  helpItem: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.sm, lineHeight: 19 },
  helpItemTitle: { fontWeight: "700", color: colors.onSurface },
});
