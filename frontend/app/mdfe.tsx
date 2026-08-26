// MDF-e (Manifesto Eletrônico de Documentos Fiscais) — Fase A: cadastro
// do manifesto + anexar NF-e/NFC-e, SEM emissão SEFAZ real ainda (Fase B,
// rodada futura). Migração de `Kontacto\FrmTraMDF.frm` — ver
// `backend/services/mdfe_service.py` pro racional completo das regras
// portadas nesta fase.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { useClienteSearchModal } from "@/src/hooks/useClienteSearchModal";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import VeiculoSearchModal, { VeiculoRow } from "@/src/components/VeiculoSearchModal";
import MunicipioSearchModal, { MunicipioRow } from "@/src/components/MunicipioSearchModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import LockedView from "@/src/components/LockedView";
import { AppModal } from "@/src/components/AppModal";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { printHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader } from "@/src/utils/print-report-header";
import { buildDamdfeHtml } from "@/src/utils/danfeFacsimile";

type Conn = Connection;

const UF_OPTS: SelectOption[] = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
  "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
].map((uf) => ({ value: uf, label: uf }));

const TIPO_TRANSP_OPTS: SelectOption[] = [
  { value: 1, label: "1 - ETC (Empresa de Transporte de Cargas)" },
  { value: 2, label: "2 - TAC (Transportador Autônomo de Cargas)" },
  { value: 3, label: "3 - CTC (Cooperativa de Transporte de Cargas)" },
];

const MDFE_AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que é o MDF-e", texto: "O Manifesto Eletrônico de Documentos Fiscais vincula uma ou mais Notas Fiscais a um único transporte — obrigatório em viagens interestaduais.", icon: { lib: "ion", name: "information-circle-outline" } },
  { titulo: "Veículo / Motorista", texto: "Obrigatórios para gravar o manifesto. Reboque e Ajudante são opcionais.", icon: { lib: "ion", name: "car-outline" } },
  { titulo: "UF Início / UF Fim", texto: "Se não escolhidas, assumem a UF da própria empresa.", icon: { lib: "ion", name: "map-outline" } },
  { titulo: "Percurso", texto: "UFs adicionais que a carga atravessa entre o início e o fim do trajeto, além das já informadas.", icon: { lib: "ion", name: "trail-sign-outline" } },
  { titulo: "Buscar e Anexar Notas", texto: "Busca Notas Fiscais ativas (não canceladas) por Cliente/Fornecedor, número, série ou período. Notas com algum problema no SEFAZ (denegada, inutilizada, em contingência) aparecem com um aviso, mas ainda podem ser anexadas — a decisão final é sua.", icon: { lib: "ion", name: "search-outline" } },
  { titulo: "Remover nota", texto: "Só é possível enquanto o manifesto ainda está em edição — depois de emitido de verdade ao SEFAZ, a lista de notas fica travada.", icon: { lib: "ion", name: "trash-outline" } },
  { titulo: "Emitir MDF-e", texto: "Transmite o manifesto de verdade ao SEFAZ. É uma ação irreversível com efeito fiscal real — exige pelo menos uma Nota Fiscal anexada, Veículo e Motorista preenchidos.", icon: { lib: "ion", name: "send-outline" } },
  { titulo: "Encerrar", texto: "Informa ao SEFAZ que o transporte chegou ao destino. Só disponível depois do manifesto ter sido transmitido — pede o Município onde o transporte foi encerrado.", icon: { lib: "ion", name: "flag-outline" } },
  { titulo: "Cancelar", texto: "Cancela o MDF-e junto ao SEFAZ — exige um motivo com pelo menos 15 caracteres. Só disponível enquanto o manifesto ainda não foi encerrado.", icon: { lib: "ion", name: "close-circle-outline" } },
  { titulo: "Consultar Situação", texto: "Consulta a situação atual do manifesto direto no SEFAZ — útil se uma emissão anterior pareceu travar sem resposta clara.", icon: { lib: "ion", name: "refresh-outline" } },
  { titulo: "Imprimir DAMDFE", texto: "Gera o Documento Auxiliar do MDF-e (DAMDFE) para impressão, disponível depois que o manifesto é transmitido.", icon: { lib: "ion", name: "print-outline" } },
];

const SITUACAO_MDFE_LABEL: Record<string, string> = {
  A: "Sem MDF-e", N: "Não Transmitido", T: "Transmitido", E: "Encerrado", C: "Cancelado",
};

function statusBadgeColor(situacao: string): string {
  switch (situacao) {
    case "T": return "#2E9E5B";
    case "E": return colors.brandPrimary;
    case "C": return colors.error;
    case "N": return "#E6A23C";
    default: return colors.muted;
  }
}

type MdfeItem = {
  codigo: number; situacao: string; data_mdfe: string | null;
  veiculo: number | null; placa: string | null;
  motorista: number | null; motorista_nome: string | null;
  ufini: string | null; uffim: string | null; qtd_notas: number;
};

type NotaAnexada = {
  codigo: number; nota: number; origem: number | null; destino: number | null;
  volumes: number | null; peso_bruto: number | null; peso_liquido: number | null;
  num_nf: number; serie_nf: string; valor_total: number; data_nf: string | null;
  fornecedor: number | null; mov: string; origem_destino: string | null;
};

type NotaBusca = {
  codigo: number; num_nf: number; serie_nf: string; fornecedor: number | null;
  mov: string; mov_descricao: string | null; valor_total: number; data_nf: string | null;
  cliente_fornecedor_nome: string; origem_destino: string | null; aviso: string | null;
};

export default function MdfeScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="MDF-e está disponível apenas no web."
        testID="mdfe-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [view, setView] = useState<"lista" | "form">("lista");
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<MdfeItem[]>([]);

  const [codigo, setCodigo] = useState<number | null>(null);
  const [veiculo, setVeiculo] = useState<number | null>(null);
  const [veiculoPlaca, setVeiculoPlaca] = useState("");
  const [reboque, setReboque] = useState<number | null>(null);
  const [reboquePlaca, setReboquePlaca] = useState("");
  const [motorista, setMotorista] = useState<number | null>(null);
  const [ajudante, setAjudante] = useState<number | null>(null);
  const [ufini, setUfini] = useState<string | null>(null);
  const [uffim, setUffim] = useState<string | null>(null);
  const [dataMdfe, setDataMdfe] = useState<string | null>(null);
  const [percurso, setPercurso] = useState<string[]>([]);
  const [percursoUfPick, setPercursoUfPick] = useState<string | null>(null);
  const [tptransp, setTptransp] = useState<number | null>(null);
  const [obs, setObs] = useState("");
  const [saving, setSaving] = useState(false);
  const [situacao, setSituacao] = useState("A");

  // ---- Fase B: emissão/encerrar/cancelar/consultar/DAMDFE ----
  const [numMdfe, setNumMdfe] = useState<number | null>(null);
  const [chaveAcesso, setChaveAcesso] = useState<string | null>(null);
  const [protocoloSefaz, setProtocoloSefaz] = useState<string | null>(null);
  const [serieMdfe, setSerieMdfe] = useState<string | null>(null);
  const [dhemi, setDhemi] = useState<string | null>(null);
  const [urlQrcode, setUrlQrcode] = useState<string | null>(null);
  const [tpAmb, setTpAmb] = useState<string | null>(null);
  const [emitindo, setEmitindo] = useState(false);
  const [consultando, setConsultando] = useState(false);
  const [imprimindo, setImprimindo] = useState(false);

  const [encerrarModalOpen, setEncerrarModalOpen] = useState(false);
  const [encerrando, setEncerrando] = useState(false);
  const [municipioEncerraCod, setMunicipioEncerraCod] = useState<number | null>(null);
  const [municipioEncerraNome, setMunicipioEncerraNome] = useState("");
  const [municipioSearchOpen, setMunicipioSearchOpen] = useState(false);
  const [municipioTerm, setMunicipioTerm] = useState("");
  const [municipioResults, setMunicipioResults] = useState<MunicipioRow[]>([]);
  const [municipioLoading, setMunicipioLoading] = useState(false);

  const [cancelarModalOpen, setCancelarModalOpen] = useState(false);
  const [cancelando, setCancelando] = useState(false);
  const [motivoCancelamento, setMotivoCancelamento] = useState("");

  const [motoristaOpts, setMotoristaOpts] = useState<SelectOption[]>([]);
  const [ajudanteOpts, setAjudanteOpts] = useState<SelectOption[]>([]);

  const [veiculoSearchOpen, setVeiculoSearchOpen] = useState(false);
  const [veiculoSearchAlvo, setVeiculoSearchAlvo] = useState<"veiculo" | "reboque">("veiculo");
  const [veiculoTerm, setVeiculoTerm] = useState("");
  const [veiculoResults, setVeiculoResults] = useState<VeiculoRow[]>([]);
  const [veiculoLoading, setVeiculoLoading] = useState(false);

  const [notasAnexadas, setNotasAnexadas] = useState<NotaAnexada[]>([]);

  const [tipoPessoa, setTipoPessoa] = useState<"C" | "F">("C");
  const [termoPessoa, setTermoPessoa] = useState("");
  const [numNf, setNumNf] = useState("");
  const [serieNf, setSerieNf] = useState("");
  const [dataDe, setDataDe] = useState<string | null>(null);
  const [dataAte, setDataAte] = useState<string | null>(null);
  const [buscandoNotas, setBuscandoNotas] = useState(false);
  const [notasEncontradas, setNotasEncontradas] = useState<NotaBusca[]>([]);
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());

  const clienteSearch = useClienteSearchModal(conn);

  const [fornecedorSearchOpen, setFornecedorSearchOpen] = useState(false);
  const [fornecedorTerm, setFornecedorTerm] = useState("");
  const [fornecedorResults, setFornecedorResults] = useState<FornecedorRow[]>([]);
  const [fornecedorLoading, setFornecedorLoading] = useState(false);

  const base = conn ? conn.api.replace(/\/+$/, "") : "";
  const qsBase = conn ? `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` : "";

  useEffect(() => {
    if (!municipioSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setMunicipioLoading(true);
      try {
        const r = await fetch(`${base}/api/mdfe/municipios?${qsBase}&search=${encodeURIComponent(municipioTerm)}`);
        const j = await r.json();
        setMunicipioResults(j?.success ? j.items || [] : []);
      } catch { setMunicipioResults([]); } finally { setMunicipioLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [municipioTerm, municipioSearchOpen, conn, base, qsBase]);

  useEffect(() => {
    if (!fornecedorSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setFornecedorLoading(true);
      try {
        const r = await fetch(`${base}/api/fornecedores?${qsBase}&search=${encodeURIComponent(fornecedorTerm)}`);
        const j = await r.json();
        setFornecedorResults(j?.success ? j.items || [] : Array.isArray(j) ? j : []);
      } catch { setFornecedorResults([]); } finally { setFornecedorLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [fornecedorTerm, fornecedorSearchOpen, conn, base, qsBase]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      try {
        const b = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        const [rm, ra] = await Promise.all([
          fetch(`${b}/api/veiculos/motoristas?${qs}`), fetch(`${b}/api/veiculos/auxiliares?${qs}`),
        ]);
        const [jm, ja] = await Promise.all([rm.json(), ra.json()]);
        setMotoristaOpts((jm?.items || []).map((i: { codigo: number; nome: string }) => ({ value: i.codigo, label: i.nome })));
        setAjudanteOpts((ja?.items || []).map((i: { codigo: number; nome: string }) => ({ value: i.codigo, label: i.nome })));
      } catch { /* silencioso */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const carregarLista = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/mdfe?${qsBase}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [conn, base, qsBase]);

  useEffect(() => {
    if (view === "lista" && conn) carregarLista();
  }, [view, conn, carregarLista]);

  const limparForm = () => {
    setCodigo(null); setVeiculo(null); setVeiculoPlaca(""); setReboque(null); setReboquePlaca("");
    setMotorista(null); setAjudante(null); setUfini(null); setUffim(null); setDataMdfe(null);
    setPercurso([]); setPercursoUfPick(null); setTptransp(null); setObs(""); setSituacao("A");
    setNotasAnexadas([]); setNotasEncontradas([]); setSelecionadas(new Set());
    setNumMdfe(null); setChaveAcesso(null); setProtocoloSefaz(null); setSerieMdfe(null);
    setDhemi(null); setUrlQrcode(null); setTpAmb(null);
  };

  const abrirNovo = () => { limparForm(); setView("form"); };

  const carregarMdfe = async (cod: number) => {
    if (!conn) return;
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/mdfe/${cod}?${qsBase}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível carregar o MDF-e.")); return; }
      const m = j.mdfe;
      setCodigo(m.codigo); setVeiculo(m.veiculo); setReboque(m.reboque);
      setMotorista(m.motorista); setAjudante(m.ajudante); setUfini(m.ufini); setUffim(m.uffim);
      setDataMdfe(m.data_mdfe); setPercurso((m.percurso || "").split(",").filter(Boolean));
      setTptransp(m.tptransp); setObs(m.obs || ""); setSituacao(m.situacao || "A");
      setNotasAnexadas(j.notas || []);
      setNumMdfe(m.num_mdfe ?? null); setChaveAcesso(m.chave_acesso ?? null);
      setProtocoloSefaz(m.protocolo_sefaz ?? null); setSerieMdfe(m.serie_mdfe ?? null);
      setDhemi(m.dhemi ?? null); setUrlQrcode(m.urlqrcode ?? null); setTpAmb(m.tp_amb ?? null);
      if (!veiculoPlaca && m.placa_veiculo) setVeiculoPlaca(m.placa_veiculo);
      setView("form");
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  };

  const gravar = async () => {
    if (!conn) return;
    if (!veiculo) { fb.showWarning("Preencher o Veículo !"); return; }
    if (!motorista) { fb.showWarning("Preencher o Motorista !"); return; }
    setSaving(true);
    try {
      const payload = {
        servidor: conn.servidor, banco: conn.banco, ...auditCtx,
        codigo, data_mdfe: dataMdfe, veiculo, reboque, motorista, ajudante,
        ufini, uffim, percurso: percurso.join(","), tptransp, obs: obs.trim() || null,
      };
      const r = await fetch(`${base}/api/mdfe`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível gravar o MDF-e.")); return; }
      fb.showSuccess(j.message || "MDF-e gravado.");
      setCodigo(j.codigo);
      if (j.codigo) await carregarMdfe(j.codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setSaving(false);
    }
  };

  const excluir = async () => {
    if (!conn || !codigo) return;
    if (!window.confirm(`Deseja excluir este MDF-e (rascunho)?`)) return;
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível excluir.")); return; }
      fb.showSuccess("MDF-e excluído.");
      setView("lista");
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  // ---- Percurso ----
  const adicionarPercurso = () => {
    if (!percursoUfPick) return;
    if (percurso.includes(percursoUfPick)) { setPercursoUfPick(null); return; }
    setPercurso((p) => [...p, percursoUfPick]);
    setPercursoUfPick(null);
  };
  const removerPercurso = (uf: string) => setPercurso((p) => p.filter((x) => x !== uf));

  // ---- Busca de Veículo/Reboque ----
  const abrirBuscaVeiculo = (alvo: "veiculo" | "reboque") => {
    setVeiculoSearchAlvo(alvo);
    setVeiculoTerm(""); setVeiculoResults([]);
    setVeiculoSearchOpen(true);
  };
  useEffect(() => {
    if (!veiculoSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setVeiculoLoading(true);
      try {
        const r = await fetch(`${base}/api/veiculos?${qsBase}&search=${encodeURIComponent(veiculoTerm)}`);
        const j = await r.json();
        setVeiculoResults(j?.success ? j.items || [] : []);
      } catch { setVeiculoResults([]); } finally { setVeiculoLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [veiculoTerm, veiculoSearchOpen, conn, base, qsBase]);
  const onPickVeiculo = (v: VeiculoRow) => {
    if (veiculoSearchAlvo === "veiculo") { setVeiculo(v.codigo); setVeiculoPlaca(v.placa); }
    else { setReboque(v.codigo); setReboquePlaca(v.placa); }
    setVeiculoSearchOpen(false);
  };

  // ---- Busca de notas ----
  const buscarNotas = async () => {
    if (!conn) return;
    setBuscandoNotas(true);
    try {
      const payload = {
        servidor: conn.servidor, banco: conn.banco,
        num_nf: numNf ? Number(numNf) : null, serie_nf: serieNf || null,
        tipo_pessoa: tipoPessoa, cliente_fornecedor_termo: termoPessoa || null,
        data_nf_de: dataDe, data_nf_ate: dataAte,
      };
      const r = await fetch(`${base}/api/mdfe/notas/buscar`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const j = await r.json();
      setNotasEncontradas(j?.success ? j.items || [] : []);
      setSelecionadas(new Set());
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setBuscandoNotas(false);
    }
  };

  const toggleSelecionada = (cod: number) => {
    setSelecionadas((s) => { const n = new Set(s); if (n.has(cod)) n.delete(cod); else n.add(cod); return n; });
  };

  const incluirSelecionadas = async () => {
    if (!conn || !codigo || selecionadas.size === 0) return;
    let algumErro = false;
    for (const nota of selecionadas) {
      try {
        const r = await fetch(`${base}/api/mdfe/${codigo}/notas`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, nota, ...auditCtx }),
        });
        const j = await r.json();
        if (!j?.success) { algumErro = true; fb.showError(friendlyApiError(j, `Falha ao anexar a nota #${nota}.`)); }
        else if (j.avisos?.length) { fb.showWarning(j.avisos.join(" — "), undefined, 5000); }
      } catch (e) {
        algumErro = true;
        fb.showError(friendlyCatchError(e));
      }
    }
    if (!algumErro) fb.showSuccess("Notas anexadas ao manifesto.");
    await carregarMdfe(codigo);
    setNotasEncontradas([]); setSelecionadas(new Set());
  };

  const removerNota = async (nota: number) => {
    if (!conn || !codigo) return;
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}/notas/${nota}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível remover a nota.")); return; }
      await carregarMdfe(codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  // ---- Fase B: emitir/encerrar/cancelar/consultar/DAMDFE ----
  const emitirMdfeConfirmado = async () => {
    if (!conn || !codigo) return;
    setEmitindo(true);
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}/emitir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível emitir o MDF-e."), undefined, 5000); return; }
      fb.showSuccess(j.message || "MDF-e emitido.", undefined, 5000);
      await carregarMdfe(codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setEmitindo(false);
    }
  };
  const emitirMdfe = () => {
    fb.showConfirm(
      "Emitir este MDF-e junto ao SEFAZ? Esta ação é irreversível e tem efeito fiscal real.",
      emitirMdfeConfirmado,
      { title: "Emitir MDF-e", confirmText: "Emitir", destructive: true },
    );
  };

  const abrirEncerrarModal = () => {
    setMunicipioEncerraCod(null); setMunicipioEncerraNome("");
    setEncerrarModalOpen(true);
  };
  const confirmarEncerrar = async () => {
    if (!conn || !codigo || !municipioEncerraCod) return;
    setEncerrando(true);
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}/encerrar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, municipio_encerra: municipioEncerraCod, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível encerrar o MDF-e."), undefined, 5000); return; }
      fb.showSuccess(j.message || "MDF-e encerrado.");
      setEncerrarModalOpen(false);
      await carregarMdfe(codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setEncerrando(false);
    }
  };

  const abrirCancelarModal = () => { setMotivoCancelamento(""); setCancelarModalOpen(true); };
  const confirmarCancelar = async () => {
    if (!conn || !codigo || motivoCancelamento.trim().length < 15) return;
    setCancelando(true);
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}/cancelar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, motivo: motivoCancelamento.trim(), ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível cancelar o MDF-e."), undefined, 5000); return; }
      fb.showSuccess(j.message || "MDF-e cancelado.");
      setCancelarModalOpen(false);
      await carregarMdfe(codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setCancelando(false);
    }
  };

  const consultarSituacao = async () => {
    if (!conn || !codigo) return;
    setConsultando(true);
    try {
      const r = await fetch(`${base}/api/mdfe/${codigo}/consultar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível consultar a situação.")); return; }
      fb.showSuccess(j.message || "Situação consultada.");
      await carregarMdfe(codigo);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setConsultando(false);
    }
  };

  const imprimirDamdfe = async () => {
    if (!conn || !codigo) return;
    setImprimindo(true);
    try {
      const empresa = await fetchEmpresaHeader(base, conn.servidor, conn.banco);
      const motoristaNome = motoristaOpts.find((o) => o.value === motorista)?.label || null;
      printHtml(
        buildDamdfeHtml(empresa, {
          num_mdfe: numMdfe, serie: serieMdfe, chave_acesso: chaveAcesso, protocolo_sefaz: protocoloSefaz,
          dhemi, situacao, veiculo_placa: veiculoPlaca, motorista_nome: motoristaNome,
          ufini, uffim, percurso: percurso.join(","), tp_amb: tpAmb, url_qrcode: urlQrcode,
          notas: notasAnexadas.map((n) => ({ num_nf: n.num_nf, serie_nf: n.serie_nf, valor_total: n.valor_total })),
        }),
        "DAMDFE",
      );
    } finally {
      setImprimindo(false);
    }
  };

  const podeEditarNotas = situacao === "A" || situacao === "N";
  const canGravar = can("MDFE.GRAVAR");
  const canExcluir = can("MDFE.EXCLUIR");
  const canEmitir = can("MDFE.EMITIR");
  const canEncerrar = can("MDFE.ENCERRAR");
  const canCancelar = can("MDFE.CANCELAR");
  const canConsultar = can("MDFE.CONSULTAR");
  const canImprimir = can("MDFE.IMPRIMIR");

  // ============ View: Lista ============
  if (view === "lista") {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]} testID="mdfe-screen">
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} testID="mdfe-back">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Text style={styles.headerTitle} numberOfLines={1}>MDF-e</Text>
          <IconButtonWithTooltip
            icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)}
            size={20} color={colors.onBrandPrimary} testID="mdfe-ajuda"
          />
          {canGravar ? (
            <Pressable onPress={abrirNovo} hitSlop={12} testID="mdfe-novo">
              <Ionicons name="add-circle-outline" size={24} color={colors.onBrandPrimary} />
            </Pressable>
          ) : <View style={{ width: 24 }} />}
        </View>
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShell}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 20 }} /> : null}
            {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum MDF-e cadastrado.</Text> : null}
            {items.map((it) => (
              <Pressable key={it.codigo} onPress={() => carregarMdfe(it.codigo)} style={styles.row} testID={`mdfe-row-${it.codigo}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>MDF-e #{it.codigo} — {it.placa || "sem veículo"}</Text>
                  <Text style={styles.rowSub}>
                    {it.motorista_nome || "sem motorista"} · {it.ufini || "?"} → {it.uffim || "?"} · {it.qtd_notas} nota(s)
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
          </View>
        </ScrollView>
        <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="MDF-e — Ajuda" itens={MDFE_AJUDA_ITENS} />
      </SafeAreaView>
    );
  }

  // ============ View: Form ============
  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="mdfe-form">
      <View style={styles.header}>
        <Pressable onPress={() => setView("lista")} hitSlop={12} testID="mdfe-form-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>{codigo ? `MDF-e #${codigo}` : "Novo MDF-e"}</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)}
          size={20} color={colors.onBrandPrimary} testID="mdfe-form-ajuda"
        />
        {canGravar ? (
          <Pressable onPress={gravar} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.7 }]} testID="mdfe-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <><Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} /><Text style={styles.saveLabel}>Gravar</Text></>
            )}
          </Pressable>
        ) : <View style={{ width: 60 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {codigo ? (
            <View style={styles.card} testID="mdfe-status-card">
              <View style={styles.statusRow}>
                <View style={[styles.statusBadge, { backgroundColor: statusBadgeColor(situacao) }]}>
                  <Text style={styles.statusBadgeText}>{SITUACAO_MDFE_LABEL[situacao] || situacao}</Text>
                </View>
                {numMdfe ? <Text style={styles.statusInfo}>Nº {numMdfe}{serieMdfe ? ` / série ${serieMdfe}` : ""}</Text> : null}
                {protocoloSefaz ? <Text style={styles.statusInfo}>Protocolo {protocoloSefaz}</Text> : null}
              </View>
              {chaveAcesso ? <Text style={styles.statusChave}>{chaveAcesso}</Text> : null}

              <View style={styles.actionsRow}>
                {(situacao === "A" || situacao === "N") && canEmitir ? (
                  <Pressable onPress={emitirMdfe} disabled={emitindo} style={[styles.actionBtn, styles.actionBtnPrimary, emitindo && { opacity: 0.7 }]} testID="mdfe-emitir">
                    {emitindo ? <ActivityIndicator color="#fff" size="small" /> : (<><Ionicons name="send-outline" size={16} color="#fff" /><Text style={styles.actionBtnPrimaryText}>Emitir MDF-e</Text></>)}
                  </Pressable>
                ) : null}
                {situacao === "T" && canEncerrar ? (
                  <Pressable onPress={abrirEncerrarModal} style={styles.actionBtn} testID="mdfe-abrir-encerrar">
                    <Ionicons name="flag-outline" size={16} color={colors.brandPrimary} /><Text style={styles.actionBtnText}>Encerrar</Text>
                  </Pressable>
                ) : null}
                {situacao === "T" && canCancelar ? (
                  <Pressable onPress={abrirCancelarModal} style={styles.actionBtn} testID="mdfe-abrir-cancelar">
                    <Ionicons name="close-circle-outline" size={16} color={colors.error} /><Text style={[styles.actionBtnText, { color: colors.error }]}>Cancelar</Text>
                  </Pressable>
                ) : null}
                {chaveAcesso && canConsultar ? (
                  <Pressable onPress={consultarSituacao} disabled={consultando} style={[styles.actionBtn, consultando && { opacity: 0.7 }]} testID="mdfe-consultar">
                    {consultando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (<><Ionicons name="refresh-outline" size={16} color={colors.brandPrimary} /><Text style={styles.actionBtnText}>Consultar Situação</Text></>)}
                  </Pressable>
                ) : null}
                {(situacao === "T" || situacao === "E" || situacao === "C") && canImprimir ? (
                  <Pressable onPress={imprimirDamdfe} disabled={imprimindo} style={[styles.actionBtn, imprimindo && { opacity: 0.7 }]} testID="mdfe-imprimir-damdfe">
                    {imprimindo ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (<><Ionicons name="print-outline" size={16} color={colors.brandPrimary} /><Text style={styles.actionBtnText}>Imprimir DAMDFE</Text></>)}
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : null}

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Identificação</Text>
            <View style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>Veículo *</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <TextInput value={veiculoPlaca} editable={false} placeholder="Buscar…" placeholderTextColor={colors.muted} style={[styles.input, { flex: 1 }]} testID="mdfe-veiculo" />
                  <IconButtonWithTooltip icon="search-outline" label="Buscar Veículo" onPress={() => abrirBuscaVeiculo("veiculo")} size={20} color={colors.brandPrimary} testID="mdfe-veiculo-buscar" />
                </View>
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Reboque</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <TextInput value={reboquePlaca} editable={false} placeholder="Opcional…" placeholderTextColor={colors.muted} style={[styles.input, { flex: 1 }]} testID="mdfe-reboque" />
                  <IconButtonWithTooltip icon="search-outline" label="Buscar Reboque" onPress={() => abrirBuscaVeiculo("reboque")} size={20} color={colors.brandPrimary} testID="mdfe-reboque-buscar" />
                </View>
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Data</Text>
                <WebDateField value={dataMdfe} onChange={setDataMdfe} testID="mdfe-data" />
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>Motorista *</Text>
                <SelectField value={motorista} onChange={(v) => setMotorista(v == null ? null : Number(v))} options={motoristaOpts} placeholder="Selecione" compactWeb testID="mdfe-motorista" modalTitle="Motorista" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Ajudante</Text>
                <SelectField value={ajudante} onChange={(v) => setAjudante(v == null ? null : Number(v))} options={ajudanteOpts} placeholder="Opcional" allowClear compactWeb testID="mdfe-ajudante" modalTitle="Ajudante" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Tipo Transportador</Text>
                <SelectField value={tptransp} onChange={(v) => setTptransp(v == null ? null : Number(v))} options={TIPO_TRANSP_OPTS} placeholder="Selecione" allowClear compactWeb testID="mdfe-tptransp" modalTitle="Tipo de Transportador" />
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>UF Início</Text>
                <SelectField value={ufini} onChange={(v) => setUfini(v == null ? null : String(v))} options={UF_OPTS} placeholder="UF da empresa" allowClear compactWeb testID="mdfe-ufini" modalTitle="UF Início" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>UF Fim</Text>
                <SelectField value={uffim} onChange={(v) => setUffim(v == null ? null : String(v))} options={UF_OPTS} placeholder="UF da empresa" allowClear compactWeb testID="mdfe-uffim" modalTitle="UF Fim" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Percurso (UFs adicionais)</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <View style={{ flex: 1 }}>
                    <SelectField value={percursoUfPick} onChange={(v) => setPercursoUfPick(v == null ? null : String(v))} options={UF_OPTS} placeholder="UF" compactWeb testID="mdfe-percurso-uf" modalTitle="Adicionar UF ao Percurso" />
                  </View>
                  <IconButtonWithTooltip icon="add-circle-outline" label="Adicionar ao Percurso" onPress={adicionarPercurso} size={22} color={colors.brandPrimary} testID="mdfe-percurso-add" />
                </View>
              </View>
            </View>
            {percurso.length > 0 ? (
              <View style={styles.chipsRow}>
                {percurso.map((uf) => (
                  <Pressable key={uf} onPress={() => removerPercurso(uf)} style={styles.chip} testID={`mdfe-percurso-chip-${uf}`}>
                    <Text style={styles.chipText}>{uf}</Text>
                    <Ionicons name="close" size={13} color={colors.brandPrimary} />
                  </Pressable>
                ))}
              </View>
            ) : null}
            <Text style={styles.label}>Observações</Text>
            <TextInput value={obs} onChangeText={setObs} multiline style={[styles.input, { minHeight: 60 }]} placeholder="Opcional" placeholderTextColor={colors.muted} testID="mdfe-obs" />

            {codigo && canExcluir ? (
              <Pressable onPress={excluir} style={[styles.dangerBtn, { marginTop: spacing.md }]} testID="mdfe-excluir">
                <Text style={styles.dangerBtnText}>Excluir MDF-e</Text>
              </Pressable>
            ) : null}
          </View>

          {codigo ? (
            <>
              <View style={styles.card}>
                <AccordionSection title="Buscar e Anexar Notas" defaultExpanded={false} testID="mdfe-buscar-notas">
                  {!podeEditarNotas ? (
                    <Text style={styles.hint}>Este manifesto não está mais em edição — a lista de notas está travada.</Text>
                  ) : (
                    <>
                      <View style={styles.chipsRow}>
                        <Pressable onPress={() => setTipoPessoa("C")} style={[styles.tipoChip, tipoPessoa === "C" && styles.tipoChipSel]} testID="mdfe-tipo-cliente">
                          <Text style={[styles.tipoChipText, tipoPessoa === "C" && styles.tipoChipTextSel]}>Cliente</Text>
                        </Pressable>
                        <Pressable onPress={() => setTipoPessoa("F")} style={[styles.tipoChip, tipoPessoa === "F" && styles.tipoChipSel]} testID="mdfe-tipo-fornecedor">
                          <Text style={[styles.tipoChipText, tipoPessoa === "F" && styles.tipoChipTextSel]}>Fornecedor</Text>
                        </Pressable>
                      </View>
                      <View style={styles.rowFields}>
                        <View style={styles.colThird}>
                          <Text style={styles.label}>{tipoPessoa === "C" ? "Cliente" : "Fornecedor"}</Text>
                          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                            <TextInput
                              value={termoPessoa} onChangeText={setTermoPessoa}
                              style={[styles.input, { flex: 1 }]} placeholder="Nome ou código…" placeholderTextColor={colors.muted}
                              testID="mdfe-termo-pessoa"
                            />
                            <IconButtonWithTooltip
                              icon="search-outline" label={`Buscar ${tipoPessoa === "C" ? "Cliente" : "Fornecedor"}`}
                              onPress={() => (tipoPessoa === "C" ? clienteSearch.openModal() : setFornecedorSearchOpen(true))}
                              size={20} color={colors.brandPrimary} testID="mdfe-termo-pessoa-buscar"
                            />
                          </View>
                        </View>
                        <View style={styles.colThird}>
                          <Text style={styles.label}>Número NF</Text>
                          <TextInput value={numNf} onChangeText={setNumNf} keyboardType="number-pad" style={styles.input} testID="mdfe-num-nf" />
                        </View>
                        <View style={styles.colThird}>
                          <Text style={styles.label}>Série</Text>
                          <TextInput value={serieNf} onChangeText={setSerieNf} style={styles.input} testID="mdfe-serie-nf" />
                        </View>
                      </View>
                      <View style={styles.rowFields}>
                        <View style={styles.colThird}>
                          <Text style={styles.label}>Data De</Text>
                          <WebDateField value={dataDe} onChange={(v) => { setDataDe(v || null); if (v) setDataAte(v); }} testID="mdfe-data-de" />
                        </View>
                        <View style={styles.colThird}>
                          <Text style={styles.label}>Data Até</Text>
                          <WebDateField value={dataAte} onChange={(v) => setDataAte(v || null)} testID="mdfe-data-ate" />
                        </View>
                        <View style={styles.colThird}>
                          <Text style={styles.label}> </Text>
                          <Pressable onPress={buscarNotas} disabled={buscandoNotas} style={[styles.secondaryBtn, buscandoNotas && { opacity: 0.6 }]} testID="mdfe-buscar-notas-btn">
                            {buscandoNotas ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.secondaryBtnText}>Buscar</Text>}
                          </Pressable>
                        </View>
                      </View>

                      {notasEncontradas.length > 0 ? (
                        <View style={{ marginTop: spacing.sm }}>
                          {notasEncontradas.map((n) => (
                            <Pressable key={n.codigo} onPress={() => toggleSelecionada(n.codigo)} style={styles.notaRow} testID={`mdfe-nota-busca-${n.codigo}`}>
                              <Ionicons name={selecionadas.has(n.codigo) ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                              <View style={{ flex: 1, marginLeft: spacing.sm }}>
                                <Text style={styles.rowTitle}>NF {n.num_nf}/{n.serie_nf} — {n.cliente_fornecedor_nome || "—"}</Text>
                                <Text style={styles.rowSub}>{n.mov_descricao || n.mov} · R$ {(n.valor_total || 0).toFixed(2)}</Text>
                                {n.aviso ? <Text style={styles.aviso}>{n.aviso}</Text> : null}
                              </View>
                            </Pressable>
                          ))}
                          <Pressable onPress={incluirSelecionadas} disabled={selecionadas.size === 0} style={[styles.primaryBtn, selecionadas.size === 0 && { opacity: 0.5 }]} testID="mdfe-incluir-selecionadas">
                            <Text style={styles.primaryBtnText}>Incluir Selecionadas ({selecionadas.size})</Text>
                          </Pressable>
                        </View>
                      ) : null}
                    </>
                  )}
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <Text style={styles.sectionTitle}>Notas Anexadas ({notasAnexadas.length})</Text>
                {notasAnexadas.length === 0 ? <Text style={styles.empty}>Nenhuma nota anexada ainda.</Text> : null}
                {notasAnexadas.map((n) => (
                  <View key={n.codigo} style={styles.notaRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowTitle}>NF {n.num_nf}/{n.serie_nf}</Text>
                      <Text style={styles.rowSub}>R$ {(n.valor_total || 0).toFixed(2)} · {n.volumes || 0} vol. · {n.peso_bruto || 0} kg</Text>
                    </View>
                    {podeEditarNotas ? (
                      <IconButtonWithTooltip icon="trash-outline" label="Remover" onPress={() => removerNota(n.nota)} size={18} color={colors.error} testID={`mdfe-remover-nota-${n.nota}`} />
                    ) : null}
                  </View>
                ))}
              </View>
            </>
          ) : (
            <Text style={styles.hint}>Grave o MDF-e primeiro para poder anexar Notas Fiscais.</Text>
          )}
        </View>
      </ScrollView>

      <VeiculoSearchModal
        visible={veiculoSearchOpen} onClose={() => setVeiculoSearchOpen(false)}
        term={veiculoTerm} setTerm={setVeiculoTerm} loading={veiculoLoading} results={veiculoResults} onPick={onPickVeiculo}
      />
      <ClientSearchModal
        visible={clienteSearch.open} onClose={clienteSearch.closeModal}
        term={clienteSearch.term} setTerm={clienteSearch.setTerm} loading={clienteSearch.loading} results={clienteSearch.results}
        onPick={(c) => { setTermoPessoa(c.nome); clienteSearch.closeModal(); }}
        onCreate={clienteSearch.closeModal}
      />
      <FornecedorSearchModal
        visible={fornecedorSearchOpen} onClose={() => setFornecedorSearchOpen(false)}
        term={fornecedorTerm} setTerm={setFornecedorTerm} loading={fornecedorLoading} results={fornecedorResults}
        onPick={(f) => { setTermoPessoa(f.fantasia || f.nome); setFornecedorSearchOpen(false); }}
      />
      <MunicipioSearchModal
        visible={municipioSearchOpen} onClose={() => setMunicipioSearchOpen(false)}
        term={municipioTerm} setTerm={setMunicipioTerm} loading={municipioLoading} results={municipioResults}
        onPick={(m) => { setMunicipioEncerraCod(m.codigo); setMunicipioEncerraNome(`${m.descricao}${m.uf ? `/${m.uf}` : ""}`); setMunicipioSearchOpen(false); }}
      />

      <AppModal visible={encerrarModalOpen} transparent animationType="fade" onRequestClose={() => setEncerrarModalOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setEncerrarModalOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Encerrar MDF-e #{codigo}</Text>
              <Pressable onPress={() => setEncerrarModalOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>Informa ao SEFAZ que este transporte chegou ao destino.</Text>
            <Text style={[styles.label, { marginTop: spacing.sm }]}>Município de Encerramento *</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
              <TextInput value={municipioEncerraNome} editable={false} placeholder="Buscar…" placeholderTextColor={colors.muted} style={[styles.input, { flex: 1 }]} testID="mdfe-municipio-encerra" />
              <IconButtonWithTooltip icon="search-outline" label="Buscar Município" onPress={() => { setMunicipioTerm(""); setMunicipioResults([]); setMunicipioSearchOpen(true); }} size={20} color={colors.brandPrimary} testID="mdfe-municipio-encerra-buscar" />
            </View>
            <View style={styles.modalActionsRow}>
              <Pressable
                onPress={confirmarEncerrar} disabled={encerrando || !municipioEncerraCod}
                style={[styles.primaryBtn, (encerrando || !municipioEncerraCod) && { opacity: 0.5 }]} testID="mdfe-confirmar-encerrar"
              >
                {encerrando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Encerrar MDF-e</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={cancelarModalOpen} transparent animationType="fade" onRequestClose={() => setCancelarModalOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCancelarModalOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Cancelar MDF-e #{codigo}</Text>
              <Pressable onPress={() => setCancelarModalOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>Cancela o documento fiscal junto ao SEFAZ — ação irreversível.</Text>
            <Text style={[styles.label, { marginTop: spacing.sm }]}>Motivo do cancelamento (mínimo 15 caracteres)</Text>
            <TextInput
              value={motivoCancelamento} onChangeText={setMotivoCancelamento}
              style={[styles.input, { minHeight: 72 }]} multiline
              placeholder="Descreva o motivo do cancelamento…" placeholderTextColor={colors.muted}
              testID="mdfe-motivo-cancelamento"
            />
            <View style={styles.modalActionsRow}>
              <Pressable
                onPress={confirmarCancelar} disabled={cancelando || motivoCancelamento.trim().length < 15}
                style={[styles.primaryBtn, { backgroundColor: colors.error }, (cancelando || motivoCancelamento.trim().length < 15) && { opacity: 0.5 }]}
                testID="mdfe-confirmar-cancelar"
              >
                {cancelando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Cancelar MDF-e</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="MDF-e — Ajuda" itens={MDFE_AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  headerTitle: { flex: 1, fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.md },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.sm, textTransform: "uppercase" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colThird: { flex: 1 },
  hint: { fontSize: 12, color: colors.muted, fontStyle: "italic", marginTop: spacing.sm },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.sm },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary,
    borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  tipoChip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 6 },
  tipoChipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoChipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  tipoChipTextSel: { color: colors.onBrandPrimary },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center", marginTop: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },

  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  statusBadge: { borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 5 },
  statusBadgeText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  statusInfo: { fontSize: 12, color: colors.onSurface, fontWeight: "600" },
  statusChave: { fontSize: 11, color: colors.muted, fontFamily: Platform.OS === "web" ? "monospace" : undefined, marginTop: 4 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  actionBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.brandPrimary,
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  actionBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  actionBtnPrimary: { backgroundColor: colors.brandPrimary },
  actionBtnPrimaryText: { color: "#fff", fontWeight: "700", fontSize: 13 },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 420, borderWidth: 1, borderColor: colors.border },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },

  secondaryBtn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center", justifyContent: "center" },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  dangerBtn: { borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingVertical: 10, alignItems: "center" },
  dangerBtnText: { color: colors.error, fontWeight: "600", fontSize: 13 },
  empty: { color: colors.muted, fontSize: 13, textAlign: "center", paddingVertical: spacing.md },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  notaRow: {
    flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  aviso: { fontSize: 11, color: colors.warning, marginTop: 2, fontStyle: "italic" },
});
