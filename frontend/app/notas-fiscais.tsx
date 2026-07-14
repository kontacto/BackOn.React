import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import {
  WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER,
} from "@/src/theme/webLayout";

type Conn = Connection;

// Cadastros > Notas Fiscais (Fase 1 — CRUD sem emissão fiscal, ver
// backend/services/notas_fiscais_service.py pro mapeamento completo de
// regras e pendências). Migração de FrmManRec.frm ("Manutenção de Nota
// Fiscal"). Esta tela NÃO emite NFe/NFSe real — DANFE, XML, Carta de
// Correção, Cancelamento/Inutilização online no SEFAZ ficam de fora até
// termos um provedor fiscal Python (ver PENDENCIAS.md).
type TipoMovNF = {
  codigo: string; descricao: string; origem_destino: string;
  atualiza_est: string; transf_pagar: string; cfop: string; cfop_fora: string;
  tipo_doc: number | null; itens: string;
};

type ItemRow = {
  codigo_int: string; descricao?: string; cod_fiscal?: string; cod_contabil?: number | null;
  tributacao?: string; qtd: number; qtd_un_compra?: number | null; p_unit: number;
  desconto?: number; valor_total: number;
  alqt_icms?: number | null; reducao_base_icms?: number | null;
  base_icms?: number | null; valor_icms?: number | null;
  base_ipi?: number | null; alqt_ipi?: number | null; valor_ipi?: number | null;
  base_sub?: number | null; valor_sub?: number | null;
  base_iss?: number | null; valor_iss?: number | null;
  frete?: number | null; seguro?: number | null; despesas?: number | null;
  tributacao_pis?: number | null; base_pis?: number | null; alqt_pis?: number | null; valor_pis?: number | null;
  tributacao_cofins?: number | null; base_cofins?: number | null; alqt_cofins?: number | null; valor_cofins?: number | null;
};

type VencRow = { data_venc: string; valor: number };

type ConsultaRow = {
  codigo: number; num_nf: number; serie_nf: string; fornecedor: number; mov: string;
  mov_descricao: string; cfop: string; uf: string; data_nf: string | null; data_mov: string | null;
  valor_total: number; situacao: string; chave_acesso: string | null; cliente_fornecedor_nome: string;
};

const SITUACAO_LABEL: Record<string, string> = {
  D: "Digitando", A: "Ativa", C: "Cancelada", E: "Erro de Crítica", L: "Liberada",
};

const numOrNull = (v: string) => {
  const n = parseFloat((v || "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
};
const fmt = (v: number | null | undefined) => (v == null ? "" : String(v));
const isoToBR = (iso: string | null) => {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};

export default function NotasFiscaisScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Notas Fiscais está disponível apenas no web."
        testID="notas-fiscais-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [view, setView] = useState<"lista" | "form">("lista");
  const [tab, setTab] = useState<"principais" | "itens" | "vencimentos" | "obs">("principais");

  const [codigo, setCodigo] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string>("D");
  const [situacaoNfe, setSituacaoNfe] = useState<number | null>(null);
  const editing = codigo != null;

  const [cab, setCab] = useState<Record<string, any>>({});
  const setC = (k: string, v: any) => setCab((prev) => ({ ...prev, [k]: v }));

  const [itens, setItens] = useState<ItemRow[]>([]);
  const [vencimentos, setVencimentos] = useState<VencRow[]>([]);

  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const [tipoMovFull, setTipoMovFull] = useState<TipoMovNF[]>([]);
  const [tipoDocOpts, setTipoDocOpts] = useState<SelectOption[]>([]);
  const [ufOpts, setUfOpts] = useState<SelectOption[]>([]);

  const tipoMovOpts = useMemo<SelectOption[]>(
    () => tipoMovFull.map((t) => ({ value: t.codigo, label: `${t.codigo} - ${t.descricao}` })),
    [tipoMovFull]
  );
  const movSelecionado = useMemo(() => tipoMovFull.find((t) => t.codigo === cab.mov) || null, [tipoMovFull, cab.mov]);
  const isFornecedor = movSelecionado?.origem_destino === "F";

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [pessoaNome, setPessoaNome] = useState("");

  const [itemDraft, setItemDraft] = useState<Partial<ItemRow>>({});
  const setItemField = (k: keyof ItemRow, v: any) => setItemDraft((p) => ({ ...p, [k]: v }));
  const [vencData, setVencData] = useState("");
  const [vencValor, setVencValor] = useState("");

  // ---- busca de produto/serviço pela descrição (aba Itens) ----
  const [descSearchOpen, setDescSearchOpen] = useState(false);
  const [descSearchResults, setDescSearchResults] = useState<{ tipo: string; codigo: string; descricao: string }[]>([]);

  // ---- filtros da Consulta (conferidos contra o FrmConNF.frm real,
  // 2026-07-13 — "UF" e faixa de "Vencimento" NÃO existem nesse form,
  // removidos; "Código da NF" e "Data Entrada/Saída" existem, adicionados) ----
  const [fCodigo, setFCodigo] = useState("");
  const [fNumNf, setFNumNf] = useState("");
  const [fSerieNf, setFSerieNf] = useState("");
  const [fCfop, setFCfop] = useState("");
  const [fMov, setFMov] = useState<string | null>(null);
  const [fEntrada, setFEntrada] = useState(true);
  const [fSaida, setFSaida] = useState(true);
  const [fSituacao, setFSituacao] = useState<"A" | "C" | "T">("T");
  const [fTipoPessoa, setFTipoPessoa] = useState<"C" | "F">("C");
  const [fTermo, setFTermo] = useState("");
  const [fDataNfDe, setFDataNfDe] = useState("");
  const [fDataNfAte, setFDataNfAte] = useState("");
  const [fDataMovDe, setFDataMovDe] = useState("");
  const [fDataMovAte, setFDataMovAte] = useState("");
  const [gridLoading, setGridLoading] = useState(false);
  const [gridItems, setGridItems] = useState<ConsultaRow[]>([]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);

      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      try {
        const r1 = await fetch(`${base}/api/tipo-mov-nf?${qs}`);
        const j1 = await r1.json();
        if (j1?.success) setTipoMovFull(j1.items || []);
      } catch { /* opcional */ }
      try {
        const r2 = await fetch(`${base}/api/tipo-doc?${qs}`);
        const j2 = await r2.json();
        if (j2?.success) setTipoDocOpts((j2.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      } catch { /* opcional */ }
      try {
        const r3 = await fetch(`${base}/api/uf?${qs}`);
        const j3 = await r3.json();
        if (j3?.success) setUfOpts((j3.items || []).map((i: any) => ({ value: i.codigo, label: i.codigo })));
      } catch { /* opcional */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // ---- busca de cliente/fornecedor (reaproveita ClientSearchModal) ----
  useEffect(() => {
    if (!searchOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
        let items: ClienteRow[] = [];
        if (isFornecedor) {
          const r = await fetch(`${base}/api/fornecedores?${qs}&search=${encodeURIComponent(searchTerm)}`);
          const j = await r.json();
          items = (j?.items || []).map((f: any) => ({
            codigo: f.codigo_int, nome: f.nome, cgc_cpf: f.codigo || "", telefone: "",
          }));
        } else {
          const r = await fetch(`${base}/api/clientes/find/search?${qs}&term=${encodeURIComponent(searchTerm)}`);
          const j = await r.json();
          items = j?.items || [];
        }
        setSearchResults(items);
      } catch { setSearchResults([]); } finally { setSearchLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, searchOpen, conn, isFornecedor]);

  const onPickPessoa = (p: ClienteRow) => {
    setC("fornecedor", p.codigo);
    setPessoaNome(p.nome);
    setSearchOpen(false);
    setSearchTerm("");
  };

  // ---- busca de produto/serviço pela Descrição (aba Itens) ----
  useEffect(() => {
    if (!descSearchOpen || !conn) return;
    const termo = (itemDraft.descricao || "").trim();
    if (termo.length < 2) { setDescSearchResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
        const r = await fetch(`${base}/api/produtos-servicos?${qs}&search=${encodeURIComponent(termo)}&tipo=all&size=10`);
        const j = await r.json();
        setDescSearchResults(j?.items || []);
      } catch { setDescSearchResults([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [itemDraft.descricao, descSearchOpen, conn]);

  const onChangeMov = (novoMov: string | number | null) => {
    const mov = String(novoMov || "");
    setC("mov", mov);
    const tm = tipoMovFull.find((t) => t.codigo === mov);
    if (tm) {
      if (!cab.cfop) setC("cfop", tm.cfop);
      if (!cab.tipo_doc && tm.tipo_doc) setC("tipo_doc", tm.tipo_doc);
    }
    // Mudar de Cliente pra Fornecedor (ou vice-versa) invalida a pessoa já escolhida.
    setC("fornecedor", null);
    setPessoaNome("");
  };

  // ---- carregar nota existente ----
  const carregar = useCallback(async (cod: number) => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/notas-fiscais/${cod}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao carregar Nota Fiscal."); return; }
      setCab(j.cabecalho || {});
      setSituacao(j.cabecalho?.situacao || "D");
      setSituacaoNfe(j.cabecalho?.situacao_nfe ?? null);
      setItens((j.itens || []).map((it: any) => ({ ...it })));
      setVencimentos((j.vencimentos || []).map((v: any) => ({ data_venc: v.data_venc, valor: v.valor })));
      setCodigo(cod);
      setView("form");
      setTab("principais");

      // Resolve nome da pessoa pra exibição (best-effort).
      const fornecedorId = j.cabecalho?.fornecedor;
      if (fornecedorId) {
        const tm = tipoMovFull.find((t) => t.codigo === j.cabecalho?.mov);
        try {
          if (tm?.origem_destino === "F") {
            const rf = await fetch(`${base}/api/fornecedores/${fornecedorId}?${qs}`);
            const jf = await rf.json();
            setPessoaNome(jf?.nome || "");
          } else {
            const rc = await fetch(`${base}/api/clientes/${fornecedorId}/resumo?${qs}`);
            const jc = await rc.json();
            setPessoaNome(jc?.nome || "");
          }
        } catch { setPessoaNome(""); }
      } else {
        setPessoaNome("");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, fb, tipoMovFull]);

  const novaNota = () => {
    setCodigo(null);
    setCab({});
    setSituacao("D");
    setSituacaoNfe(null);
    setItens([]);
    setVencimentos([]);
    setPessoaNome("");
    setView("form");
    setTab("principais");
  };

  // ---- itens ----
  const adicionarItem = () => {
    if (!(itemDraft.codigo_int || "").trim()) { fb.showError("Informe o Código do Produto/Serviço."); return; }
    if (!itemDraft.qtd) { fb.showError("Informe a Quantidade."); return; }
    const qtd = Number(itemDraft.qtd) || 0;
    const p_unit = Number(itemDraft.p_unit) || 0;
    const desconto = Number(itemDraft.desconto) || 0;
    const valor_total = itemDraft.valor_total ?? (qtd * p_unit - desconto);
    setItens((prev) => [...prev, { ...itemDraft, qtd, p_unit, desconto, valor_total } as ItemRow]);
    setItemDraft({});
  };
  const removerItem = (idx: number) => setItens((prev) => prev.filter((_, i) => i !== idx));
  const buscarDescricaoItem = async () => {
    if (!conn || !(itemDraft.codigo_int || "").trim()) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/notas-fiscais/produto/${encodeURIComponent(itemDraft.codigo_int!)}?${qs}`);
      const j = await r.json();
      if (j?.success && j.found) {
        setItemField("descricao", j.descricao);
        if (j.cod_fiscal) setItemField("cod_fiscal", j.cod_fiscal);
      }
    } catch { /* opcional */ }
  };
  const escolherProdutoBusca = async (p: { tipo: string; codigo: string; descricao: string }) => {
    setItemField("codigo_int", p.codigo);
    setItemField("descricao", p.descricao);
    setDescSearchOpen(false);
    setDescSearchResults([]);
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/notas-fiscais/produto/${encodeURIComponent(p.codigo)}?${qs}`);
      const j = await r.json();
      if (j?.success && j.found && j.cod_fiscal) setItemField("cod_fiscal", j.cod_fiscal);
    } catch { /* opcional */ }
  };
  const somaItens = useMemo(() => itens.reduce((s, it) => s + (Number(it.valor_total) || 0), 0), [itens]);

  // ---- vencimentos ----
  const adicionarVenc = () => {
    if (!vencData || !vencValor) { fb.showError("Informe Data e Valor do vencimento."); return; }
    setVencimentos((prev) => [...prev, { data_venc: vencData, valor: numOrNull(vencValor) || 0 }]);
    setVencData(""); setVencValor("");
  };
  const removerVenc = (idx: number) => setVencimentos((prev) => prev.filter((_, i) => i !== idx));
  const somaVencimentos = useMemo(() => vencimentos.reduce((s, v) => s + (Number(v.valor) || 0), 0), [vencimentos]);

  // ---- gravar (cabeçalho + itens + vencimentos, tudo junto) ----
  const gravar = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, codigo, ...auditCtx, ...cab,
      };
      const r = await fetch(`${base}/api/notas-fiscais/cabecalho`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao gravar cabeçalho."); return; }
      const novoCodigo = j.codigo as number;

      if (itens.length > 0 || editing) {
        const ri = await fetch(`${base}/api/notas-fiscais/${novoCodigo}/itens`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, itens }),
        });
        const ji = await ri.json();
        if (!ji?.success) { fb.showError(ji?.message || "Falha ao gravar itens."); return; }
      }
      if (vencimentos.length > 0 || editing) {
        const rv = await fetch(`${base}/api/notas-fiscais/${novoCodigo}/vencimentos`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, vencimentos }),
        });
        const jv = await rv.json();
        if (!jv?.success) { fb.showError(jv?.message || "Falha ao gravar vencimentos."); return; }
      }

      fb.showSuccess("Nota Fiscal gravada com sucesso.");
      await carregar(novoCodigo);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const criticar = async () => {
    if (!conn || !codigo) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/notas-fiscais/${codigo}/criticar?${qs}`, { method: "POST" });
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao criticar."); return; }
      setSituacao(j.situacao);
      if (j.divergencias?.length) {
        fb.showError(j.divergencias.map((d: any) => d.descricao).join(" — "));
      } else {
        fb.showSuccess("Nota Fiscal crítica: sem divergências.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const cancelar = async () => {
    if (!conn || !codigo) return;
    if (!window.confirm(`Deseja cancelar a Nota Fiscal ${cab.num_nf} série ${cab.serie_nf}?`)) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/notas-fiscais/${codigo}/cancelar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao cancelar."); return; }
      fb.showSuccess(j.message || "Nota Fiscal cancelada.");
      await carregar(codigo);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const excluir = async () => {
    if (!conn || !codigo) return;
    if (!window.confirm(`Deseja excluir definitivamente a Nota Fiscal ${cab.num_nf} série ${cab.serie_nf}?`)) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/notas-fiscais/${codigo}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Falha ao excluir."); return; }
      fb.showSuccess("Nota Fiscal excluída.");
      setView("lista");
      await selecionar();
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // ---- consulta ----
  const selecionar = useCallback(async () => {
    if (!conn) return;
    setGridLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, ...auditCtx,
        codigo: fCodigo ? numOrNull(fCodigo) : null,
        num_nf: fNumNf ? numOrNull(fNumNf) : null,
        serie_nf: fSerieNf || null, cfop: fCfop || null, mov: fMov,
        entrada: fEntrada, saida: fSaida,
        situacao: fSituacao === "T" ? null : fSituacao,
        tipo_pessoa: fTipoPessoa, cliente_fornecedor_termo: fTermo || null,
        data_nf_de: fDataNfDe || null, data_nf_ate: fDataNfAte || null,
        data_mov_de: fDataMovDe || null, data_mov_ate: fDataMovAte || null,
      };
      const r = await fetch(`${base}/api/notas-fiscais/selecionar`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      setGridItems(j?.items || []);
    } catch {
      setGridItems([]);
    } finally {
      setGridLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, fCodigo, fNumNf, fSerieNf, fCfop, fMov, fEntrada, fSaida, fSituacao, fTipoPessoa, fTermo, fDataNfDe, fDataNfAte, fDataMovDe, fDataMovAte]);

  useEffect(() => {
    if (view === "lista" && conn) selecionar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, conn]);

  const canGravar = can("NOTAS_FISCAIS.GRAVAR");
  const canCriticar = can("NOTAS_FISCAIS.CRITICAR");
  const canCancelar = can("NOTAS_FISCAIS.CANCELAR");
  const canExcluir = can("NOTAS_FISCAIS.EXCLUIR");

  // ============ View: Lista/Consulta ============
  if (view === "lista") {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]} testID="notas-fiscais-screen">
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} testID="notas-fiscais-back">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
          <Text style={styles.headerTitle} numberOfLines={1}>Notas Fiscais</Text>
          {can("NOTAS_FISCAIS.GRAVAR") ? (
            <Pressable onPress={novaNota} style={styles.saveBtn} testID="notas-fiscais-nova">
              <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Nova</Text>
            </Pressable>
          ) : <View style={{ width: 60 }} />}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Filtros</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código da NF</Text>
                  <TextInput value={fCodigo} onChangeText={setFCodigo} keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Nº da NF</Text>
                  <TextInput value={fNumNf} onChangeText={setFNumNf} keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Série</Text>
                  <TextInput value={fSerieNf} onChangeText={setFSerieNf} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>CFOP</Text>
                  <TextInput value={fCfop} onChangeText={setFCfop} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo de Movimentação</Text>
                  <SelectField value={fMov} onChange={(v) => setFMov(v as string)} options={tipoMovOpts} allowClear compactWeb searchable />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Entrada/Saída de</Text>
                                    <WebDateField value={fDataMovDe} onChange={setFDataMovDe} testID="nf-filtro-data-mov-de" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                                    <WebDateField value={fDataMovAte} onChange={setFDataMovAte} testID="nf-filtro-data-mov-ate" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Cliente/Fornecedor</Text>
                  <TextInput value={fTermo} onChangeText={setFTermo} onBlur={selecionar} onSubmitEditing={selecionar} style={styles.input} placeholder="Nome ou código" placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Tipo Pessoa</Text>
                  <SelectField
                    value={fTipoPessoa}
                    onChange={(v) => setFTipoPessoa(v as "C" | "F")}
                    options={[{ value: "C", label: "Cliente" }, { value: "F", label: "Fornecedor" }]}
                    compactWeb
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Situação</Text>
                  <SelectField
                    value={fSituacao}
                    onChange={(v) => setFSituacao(v as "A" | "C" | "T")}
                    options={[{ value: "T", label: "Todas" }, { value: "A", label: "Ativas" }, { value: "C", label: "Canceladas" }]}
                    compactWeb
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data NF de</Text>
                                    <WebDateField value={fDataNfDe} onChange={setFDataNfDe} testID="nf-filtro-data-nf-de" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                                    <WebDateField value={fDataNfAte} onChange={setFDataNfAte} testID="nf-filtro-data-nf-ate" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <Pressable onPress={() => setFEntrada((v) => !v)} style={styles.checkboxRow}>
                  <Ionicons name={fEntrada ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkboxLabel}>NF's de Entrada</Text>
                </Pressable>
                <Pressable onPress={() => setFSaida((v) => !v)} style={styles.checkboxRow}>
                  <Ionicons name={fSaida ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkboxLabel}>NF's de Saída</Text>
                </Pressable>
                <Pressable onPress={selecionar} style={[styles.primaryBtn, { flex: 1 }]} testID="notas-fiscais-selecionar">
                  {gridLoading ? <ActivityIndicator color="#fff" /> : <><Ionicons name="search" size={16} color="#fff" /><Text style={styles.primaryBtnText}>  Selecionar</Text></>}
                </Pressable>
              </View>
            </View>

            <View style={styles.card}>
              {gridItems.length === 0 ? (
                <Text style={styles.empty}>{gridLoading ? "Buscando..." : "Nenhuma Nota Fiscal encontrada — ajuste os filtros."}</Text>
              ) : (
                gridItems.map((nf) => (
                  <Pressable key={nf.codigo} onPress={() => carregar(nf.codigo)} style={styles.resultRowNf} testID={`notas-fiscais-row-${nf.codigo}`}>
                    <View style={{ flex: 2 }}>
                      <Text style={styles.resultNome} numberOfLines={1}>
                        Nº {nf.num_nf} / Série {nf.serie_nf} — {nf.mov_descricao || nf.mov}
                      </Text>
                      <Text style={styles.resultSub} numberOfLines={1}>{nf.cliente_fornecedor_nome || `#${nf.fornecedor}`}</Text>
                    </View>
                    <Text style={styles.resultSub}>{isoToBR(nf.data_nf)}</Text>
                    <Text style={styles.resultSub}>{(nf.valor_total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</Text>
                    <View style={[styles.situacaoBadge, nf.situacao === "C" && styles.situacaoBadgeCancelada, nf.situacao === "E" && styles.situacaoBadgeErro]}>
                      <Text style={styles.situacaoBadgeText}>{SITUACAO_LABEL[nf.situacao] || nf.situacao}</Text>
                    </View>
                  </Pressable>
                ))
              )}
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ============ View: Formulário ============
  const TABS: { key: typeof tab; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: "principais", label: "Dados Principais", icon: "document-text-outline" },
    { key: "itens", label: "Itens", icon: "list-outline" },
    { key: "vencimentos", label: "Vencimentos", icon: "calendar-outline" },
    { key: "obs", label: "Observações", icon: "chatbox-ellipses-outline" },
  ];

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="notas-fiscais-form">
      <View style={styles.header}>
        <Pressable onPress={() => setView("lista")} hitSlop={12} testID="notas-fiscais-form-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Nota Fiscal #${codigo}` : "Nova Nota Fiscal"}
        </Text>
        {canGravar ? (
          <Pressable onPress={gravar} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.7 }]} testID="notas-fiscais-gravar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <><Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} /><Text style={styles.saveLabel}>Gravar</Text></>
            )}
          </Pressable>
        ) : <View style={{ width: 60 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 20 }} /> : null}

          <View style={styles.tabBar}>
            {TABS.map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable key={t.key} onPress={() => setTab(t.key)} style={[styles.tabBtn, sel && styles.tabBtnSel]} testID={`notas-fiscais-tab-${t.key}`}>
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {editing ? (
            <View style={styles.statusRow}>
              <View style={[styles.situacaoBadge, situacao === "C" && styles.situacaoBadgeCancelada, situacao === "E" && styles.situacaoBadgeErro]}>
                <Text style={styles.situacaoBadgeText}>{SITUACAO_LABEL[situacao] || situacao}</Text>
              </View>
              {canCriticar ? (
                <Pressable onPress={criticar} style={styles.secondaryBtn} testID="notas-fiscais-criticar">
                  <Text style={styles.secondaryBtnText}>Criticar</Text>
                </Pressable>
              ) : null}
              {canCancelar && situacao !== "C" ? (
                <Pressable onPress={cancelar} style={styles.secondaryBtn} testID="notas-fiscais-cancelar">
                  <Text style={styles.secondaryBtnText}>Cancelar</Text>
                </Pressable>
              ) : null}
              {canExcluir && situacao === "C" ? (
                <Pressable onPress={excluir} style={styles.dangerBtn} testID="notas-fiscais-excluir">
                  <Text style={styles.dangerBtnText}>Excluir</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {tab === "principais" ? (
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo de Movimentação</Text>
                  <SelectField value={cab.mov || null} onChange={onChangeMov} options={tipoMovOpts} searchable compactWeb testID="nf-mov" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Nº da N.F.</Text>
                  <TextInput value={fmt(cab.num_nf)} onChangeText={(v) => setC("num_nf", numOrNull(v))} keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Série</Text>
                  <TextInput value={cab.serie_nf || ""} onChangeText={(v) => setC("serie_nf", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>{isFornecedor ? "Fornecedor" : "Cliente"}</Text>
                  <Pressable onPress={() => setSearchOpen(true)} style={styles.readonlyBoxPressable} testID="nf-buscar-pessoa">
                    <Text style={pessoaNome ? styles.readonlyText : styles.readonlyPlaceholder}>
                      {pessoaNome || (cab.fornecedor ? `#${cab.fornecedor}` : "Toque para selecionar…")}
                    </Text>
                    <Ionicons name="search" size={16} color={colors.brandPrimary} />
                  </Pressable>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Emissão</Text>
                                    <WebDateField value={cab.data_nf} onChange={(v) => setC("data_nf", v)} testID="nf-data-emissao" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Mov. (Entrada)</Text>
                                    <WebDateField value={cab.data_mov} onChange={(v) => setC("data_mov", v)} testID="nf-data-mov" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Saída</Text>
                                    <WebDateField value={cab.data_saida} onChange={(v) => setC("data_saida", v)} testID="nf-data-saida" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>CFOP</Text>
                  <TextInput value={cab.cfop || ""} onChangeText={(v) => setC("cfop", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>UF</Text>
                  <SelectField value={cab.uf || null} onChange={(v) => setC("uf", v)} options={ufOpts} compactWeb />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Espécie/Modelo</Text>
                  <SelectField value={cab.tipo_doc || null} onChange={(v) => setC("tipo_doc", v)} options={tipoDocOpts} searchable compactWeb />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Livro</Text>
                  <TextInput value={cab.livro || ""} onChangeText={(v) => setC("livro", v)} style={styles.input} maxLength={1} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Pagar</Text>
                  <TextInput value={cab.pagar || ""} onChangeText={(v) => setC("pagar", v)} style={styles.input} maxLength={1} placeholderTextColor={colors.muted} />
                </View>
              </View>

              <Text style={styles.sectionSubtitle}>Valores Fiscais</Text>
              <View style={styles.rowFields}>
                <NumField label="Valor Total" v={cab.valor_total} onC={(x) => setC("valor_total", x)} />
                <NumField label="Base ICMS" v={cab.base_icms} onC={(x) => setC("base_icms", x)} />
                <NumField label="Valor ICMS" v={cab.valor_icms} onC={(x) => setC("valor_icms", x)} />
                <NumField label="Base IPI" v={cab.base_ipi} onC={(x) => setC("base_ipi", x)} />
                <NumField label="Valor IPI" v={cab.valor_ipi} onC={(x) => setC("valor_ipi", x)} />
              </View>
              <View style={styles.rowFields}>
                <NumField label="Base ISS" v={cab.base_iss} onC={(x) => setC("base_iss", x)} />
                <NumField label="Valor ISS" v={cab.valor_iss} onC={(x) => setC("valor_iss", x)} />
                <NumField label="Base ICMS Subst." v={cab.base_sub} onC={(x) => setC("base_sub", x)} />
                <NumField label="Valor ICMS Subst." v={cab.valor_sub} onC={(x) => setC("valor_sub", x)} />
              </View>
              <View style={styles.rowFields}>
                <NumField label="Frete" v={cab.frete} onC={(x) => setC("frete", x)} />
                <NumField label="Seguro" v={cab.seguro} onC={(x) => setC("seguro", x)} />
                <NumField label="Outras Despesas" v={cab.despesas} onC={(x) => setC("despesas", x)} />
                <NumField label="Desconto" v={cab.desconto} onC={(x) => setC("desconto", x)} />
              </View>
              <View style={styles.rowFields}>
                <NumField label="Base FCP" v={cab.base_fcp} onC={(x) => setC("base_fcp", x)} />
                <NumField label="Valor FCP" v={cab.valor_fcp} onC={(x) => setC("valor_fcp", x)} />
                <NumField label="Base FCP Retido" v={cab.base_fcp_retido} onC={(x) => setC("base_fcp_retido", x)} />
                <NumField label="Valor FCP Retido" v={cab.valor_fcp_retido} onC={(x) => setC("valor_fcp_retido", x)} />
                <NumField label="Base FCP ST" v={cab.base_fcp_st} onC={(x) => setC("base_fcp_st", x)} />
                <NumField label="Valor FCP ST" v={cab.valor_fcp_st} onC={(x) => setC("valor_fcp_st", x)} />
              </View>

              <Text style={styles.sectionSubtitle}>Fiscal / SEFAZ (referência — emissão real não faz parte desta fase)</Text>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Chave de Acesso</Text>
                  <TextInput value={cab.chave_acesso || ""} onChangeText={(v) => setC("chave_acesso", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Protocolo SEFAZ</Text>
                  <TextInput value={cab.protocolo_sefaz || ""} onChangeText={(v) => setC("protocolo_sefaz", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
              </View>
            </View>
          ) : null}

          {tab === "itens" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Itens da Nota Fiscal</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código</Text>
                  <TextInput value={itemDraft.codigo_int || ""} onChangeText={(v) => setItemField("codigo_int", v)} onBlur={buscarDescricaoItem} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={[styles.colFlex, { position: "relative", zIndex: 10 }]}>
                  <Text style={styles.label}>Descrição</Text>
                  <TextInput
                    value={itemDraft.descricao || ""}
                    onChangeText={(v) => { setItemField("descricao", v); setDescSearchOpen(true); }}
                    onFocus={() => setDescSearchOpen(true)}
                    onBlur={() => setTimeout(() => setDescSearchOpen(false), 150)}
                    style={styles.input}
                    placeholder="Digite parte da descrição para buscar…"
                    placeholderTextColor={colors.muted}
                    testID="nf-item-descricao"
                  />
                  {descSearchOpen && descSearchResults.length > 0 ? (
                    <View style={styles.descDropdown}>
                      <ScrollView style={{ maxHeight: 220 }} keyboardShouldPersistTaps="handled">
                        {descSearchResults.map((p) => (
                          <Pressable
                            key={`${p.tipo}-${p.codigo}`}
                            onPress={() => escolherProdutoBusca(p)}
                            style={({ pressed }) => [styles.descDropdownRow, pressed && { backgroundColor: colors.brandTertiary }]}
                          >
                            <Text style={styles.resultNome} numberOfLines={1}>{p.descricao}</Text>
                            <Text style={styles.resultSub}>#{p.codigo} · {p.tipo === "S" ? "Serviço" : "Produto"}</Text>
                          </Pressable>
                        ))}
                      </ScrollView>
                    </View>
                  ) : null}
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cód. Fiscal</Text>
                  <TextInput value={itemDraft.cod_fiscal || ""} onChangeText={(v) => setItemField("cod_fiscal", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Tributação</Text>
                  <TextInput value={itemDraft.tributacao || ""} onChangeText={(v) => setItemField("tributacao", v)} style={styles.input} placeholderTextColor={colors.muted} />
                </View>
              </View>
              <View style={styles.rowFields}>
                <NumFieldDraft label="Quantidade" k="qtd" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Preço Unitário" k="p_unit" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Desconto" k="desconto" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Valor Total" k="valor_total" itemDraft={itemDraft} setItemField={setItemField} />
              </View>
              <View style={styles.rowFields}>
                <NumFieldDraft label="Base ICMS" k="base_icms" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Alíq. ICMS" k="alqt_icms" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Valor ICMS" k="valor_icms" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Base IPI" k="base_ipi" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Alíq. IPI" k="alqt_ipi" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Valor IPI" k="valor_ipi" itemDraft={itemDraft} setItemField={setItemField} />
              </View>
              <View style={styles.rowFields}>
                <NumFieldDraft label="Base Subst." k="base_sub" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Valor Subst." k="valor_sub" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Base ISS" k="base_iss" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Valor ISS" k="valor_iss" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Frete" k="frete" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Seguro" k="seguro" itemDraft={itemDraft} setItemField={setItemField} />
                <NumFieldDraft label="Despesas" k="despesas" itemDraft={itemDraft} setItemField={setItemField} />
              </View>
              <Pressable onPress={adicionarItem} style={[styles.primaryBtn, { alignSelf: "flex-start", paddingHorizontal: spacing.lg }]} testID="nf-item-adicionar">
                <Ionicons name="add" size={16} color="#fff" /><Text style={styles.primaryBtnText}>  Adicionar Item</Text>
              </Pressable>

              <View style={styles.divider} />
              {itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum item lançado.</Text>
              ) : itens.map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultNome}>{it.codigo_int} — {it.descricao || "(sem descrição)"}</Text>
                    <Text style={styles.resultSub}>
                      Qtd {it.qtd} × {(it.p_unit || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })} = {(it.valor_total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </Text>
                  </View>
                  <Pressable onPress={() => removerItem(idx)} hitSlop={8}>
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                </View>
              ))}
              <Text style={styles.totalHint}>
                Soma dos Itens: {somaItens.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                {cab.valor_total != null ? ` (Valor Total da Nota: ${Number(cab.valor_total).toLocaleString("pt-BR", { minimumFractionDigits: 2 })})` : ""}
              </Text>
            </View>
          ) : null}

          {tab === "vencimentos" ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Vencimentos</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data</Text>
                                    <WebDateField value={vencData} onChange={setVencData} testID="nf-venc-data" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor</Text>
                  <TextInput value={vencValor} onChangeText={setVencValor} keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted} />
                </View>
                <Pressable onPress={adicionarVenc} style={[styles.primaryBtn, { alignSelf: "flex-end" }]} testID="nf-venc-adicionar">
                  <Ionicons name="add" size={16} color="#fff" /><Text style={styles.primaryBtnText}>  Adicionar</Text>
                </Pressable>
              </View>
              <View style={styles.divider} />
              {vencimentos.length === 0 ? (
                <Text style={styles.empty}>Nenhum vencimento lançado.</Text>
              ) : vencimentos.map((v, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.resultNome}>{isoToBR(v.data_venc)} — {(v.valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</Text>
                  <Pressable onPress={() => removerVenc(idx)} hitSlop={8}>
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                </View>
              ))}
              <Text style={styles.totalHint}>
                Soma dos Vencimentos: {somaVencimentos.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                {cab.valor_total != null ? ` (Valor Total da Nota: ${Number(cab.valor_total).toLocaleString("pt-BR", { minimumFractionDigits: 2 })})` : ""}
              </Text>
            </View>
          ) : null}

          {tab === "obs" ? (
            <View style={styles.card}>
              <Text style={styles.label}>Observações da Nota Fiscal</Text>
              <TextInput
                value={cab.obs || ""} onChangeText={(v) => setC("obs", v)}
                style={[styles.input, styles.inputMultiline]} multiline placeholderTextColor={colors.muted}
              />
              <View style={{ height: spacing.md }} />
              <Text style={styles.label}>Observações do Livro Fiscal</Text>
              <TextInput
                value={cab.obs_livro || ""} onChangeText={(v) => setC("obs_livro", v)}
                style={[styles.input, styles.inputMultiline]} multiline placeholderTextColor={colors.muted}
              />
            </View>
          ) : null}
        </View>
      </ScrollView>

      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={onPickPessoa}
        onCreate={() => setSearchOpen(false)}
      />
    </SafeAreaView>
  );
}

function NumField({ label, v, onC }: { label: string; v: any; onC: (n: number | null) => void }) {
  return (
    <View style={styles.colNarrow}>
      <Text style={styles.label}>{label}</Text>
      <TextInput value={fmt(v)} onChangeText={(t) => onC(numOrNull(t))} keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted} />
    </View>
  );
}

function NumFieldDraft({ label, k, itemDraft, setItemField }: {
  label: string; k: keyof ItemRow; itemDraft: Partial<ItemRow>; setItemField: (k: keyof ItemRow, v: any) => void;
}) {
  return (
    <View style={styles.colNarrow}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={fmt((itemDraft as any)[k])}
        onChangeText={(t) => setItemField(k, numOrNull(t))}
        keyboardType="numeric" style={styles.input} placeholderTextColor={colors.muted}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  headerLogo: { width: 48, height: 14 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "600" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, gap: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionSubtitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.md, marginBottom: 4 },
  rowFields: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "flex-end" },
  colFlex: { flex: 1, minWidth: 180, gap: 4 },
  colNarrow: { width: 140, gap: 4 },
  colTiny: { width: 80, gap: 4 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 10,
    paddingHorizontal: 10, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, minWidth: 0,
  },
  inputMultiline: { minHeight: 100, textAlignVertical: "top" },
  readonlyBoxPressable: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 10,
    backgroundColor: colors.surfaceSecondary,
  },
  readonlyText: { fontSize: 14, color: colors.onSurface },
  readonlyPlaceholder: { fontSize: 14, color: colors.muted },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  secondaryBtn: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: spacing.md },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  dangerBtn: { borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: spacing.md },
  dangerBtnText: { color: colors.error, fontWeight: "600", fontSize: 13 },
  checkboxRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  checkboxLabel: { fontSize: 13, color: colors.onSurface },
  empty: { color: colors.muted, fontSize: 14, textAlign: "center", paddingVertical: spacing.lg },
  resultRowNf: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultNome: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted },
  situacaoBadge: { backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingVertical: 4, paddingHorizontal: 10 },
  situacaoBadgeCancelada: { backgroundColor: "#F5D0D0" },
  situacaoBadgeErro: { backgroundColor: "#FCE8B8" },
  situacaoBadgeText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },
  tabBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: spacing.md, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, color: colors.muted, fontWeight: "600" },
  tabLabelSel: { color: colors.onBrandPrimary },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  itemRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  totalHint: { fontSize: 13, color: colors.muted, marginTop: spacing.sm, fontWeight: "600" },
  descDropdown: {
    position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, zIndex: 20,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, elevation: 4, shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  descDropdownRow: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
});
