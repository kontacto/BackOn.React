import { useCallback, useEffect, useRef, useState } from "react";
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
import WhatsappButton from "@/src/components/WhatsappButton";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;

type ClienteTele = {
  codigo: number; nome: string; fantasia: string; cgc_cpf: string; data_cadastro: string | null;
  e_mail: string; contato: string; telefone: string; ultimo_contato: string | null; historico: string;
  dia_contato: number | null; data_agendamento: string | null; endereco: string;
  rota_nome: string | null; regiao_nome: string | null; segmento_nome: string | null;
  tipo_cliente_nome: string | null; funcionario_agendamento_nome: string | null;
};

type SelecionarItem = {
  codigo: number; nome: string; fantasia: string; contato: string; telefone: string;
  ultimo_contato: string | null; dia_contato_nome: string | null; dia_entrega_nome: string | null;
  data_agendamento: string | null; funcionario_agendamento_nome: string | null;
};

const pad = (n: number) => String(n).padStart(2, "0");
const isoToBR = (iso: string | null) => {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

// Cadastros > Telemarketing (gestor de comunicação com o cliente). Legado:
// FrmManTMa.frm ("TeleMarketing..."). NÃO existe tabela `telemarketing` —
// confirmado com o usuário 2026-07-12 — tudo grava em `cliente`
// (historico/ultimo_contato/DATA_AGENDAMENTO_TELEMARKETING/
// FUNCIONARIO_AGENDAMENTO_TELEMARKETING), exatamente como o `.frm`.
// Ver memória de projeto "Telemarketing" pro mapeamento completo e
// pendências (Ranking de Vendas/Vendas/Inatividade de Clientes — telas
// legadas ainda não migradas, não implementadas aqui).
export default function TelemarketingScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Telemarketing está disponível apenas no web."
        testID="telemarketing-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [usuarioNome, setUsuarioNome] = useState("Sistema");
  const [view, setView] = useState<"main" | "selecionar">("main");
  const mainScrollRef = useRef<ScrollView>(null);

  const [cliente, setCliente] = useState<ClienteTele | null>(null);
  const [waEnabled, setWaEnabled] = useState<boolean | null>(null);
  const [timestamp, setTimestamp] = useState("");
  const [texto, setTexto] = useState("");
  const [agendamento, setAgendamento] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);

  // ---- filtros "Selecionar Cliente" ----
  const [fDiaContato, setFDiaContato] = useState<number | null>(null);
  const [fDiaEntrega, setFDiaEntrega] = useState<number | null>(null);
  const [fClienteTermo, setFClienteTermo] = useState("");
  const [fVendedor, setFVendedor] = useState<number | null>(null);
  const [fRegiao, setFRegiao] = useState<number | null>(null);
  const [fSegmento, setFSegmento] = useState<string | null>(null);
  const [fRota, setFRota] = useState<number | null>(null);
  const [fTipoCliente, setFTipoCliente] = useState<number | null>(null);
  const [fSituacao, setFSituacao] = useState<string | null>(null);
  const [fCgcCpf, setFCgcCpf] = useState("");
  const [fBairro, setFBairro] = useState("");
  const [fUltContatoDe, setFUltContatoDe] = useState("");
  const [fUltContatoAte, setFUltContatoAte] = useState("");
  const [fAgendDe, setFAgendDe] = useState("");
  const [fAgendAte, setFAgendAte] = useState("");
  const [fOrdenarPor, setFOrdenarPor] = useState<"cliente" | "ultimo_contato">("ultimo_contato");

  const [diaSemanaOpts, setDiaSemanaOpts] = useState<SelectOption[]>([]);
  const [funcionariosOpts, setFuncionariosOpts] = useState<SelectOption[]>([]);
  const [regioesOpts, setRegioesOpts] = useState<SelectOption[]>([]);
  const [segmentosOpts, setSegmentosOpts] = useState<SelectOption[]>([]);
  const [rotasOpts, setRotasOpts] = useState<SelectOption[]>([]);
  const [tipoClienteOpts, setTipoClienteOpts] = useState<SelectOption[]>([]);
  const [situacaoOpts, setSituacaoOpts] = useState<SelectOption[]>([]);

  const [gridLoading, setGridLoading] = useState(false);
  const [gridItems, setGridItems] = useState<SelecionarItem[]>([]);

  const nowLabel = useCallback(() => {
    const d = new Date();
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} (Adicionado por ${usuarioNome})`;
  }, [usuarioNome]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      setUsuarioNome(String(func?.nome_guerra || func?.nome || "Sistema"));

      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const fetchOpts = async (path: string, setter: (o: SelectOption[]) => void, labelKey = "descricao", valueKey = "codigo") => {
        try {
          const r = await fetch(`${base}/api/${path}?${qs}`);
          const j = await r.json();
          if (j?.success) setter((j.items || []).map((i: any) => ({ value: i[valueKey], label: i[labelKey] })));
        } catch { /* opcional */ }
      };
      await Promise.all([
        fetchOpts("dia-semana", setDiaSemanaOpts),
        fetchOpts("funcionarios", setFuncionariosOpts, "nome_guerra", "codigo"),
        fetchOpts("regioes", setRegioesOpts),
        fetchOpts("segmentos", setSegmentosOpts),
        fetchOpts("rotas", setRotasOpts),
        fetchOpts("tipo-cliente", setTipoClienteOpts),
        fetchOpts("tabelas/situacao", setSituacaoOpts),
      ]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const carregarCliente = useCallback(async (codigo: number) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/telemarketing/cliente/${codigo}?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setCliente(j);
        setTexto("");
        setAgendamento(j.data_agendamento || null);
        setTimestamp(nowLabel());
        setView("main");
        // Volta pro topo da tela principal — pedido explícito do usuário
        // (sem isso, a página ficava na posição de rolagem de onde o
        // cliente foi selecionado, escondendo o card "Contato Atual").
        requestAnimationFrame(() => {
          mainScrollRef.current?.scrollTo({ y: 0, animated: false });
          if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "auto" });
        });
      } else {
        fb.showError(j?.message || "Falha ao carregar cliente.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, nowLabel]);

  useEffect(() => {
    if (!searchOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(searchTerm)}`;
        const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
        const j = await r.json();
        setSearchResults(j?.items || []);
      } catch { setSearchResults([]); } finally { setSearchLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, searchOpen, conn]);

  const limpar = () => { setTexto(""); setTimestamp(nowLabel()); };

  const gravar = async () => {
    if (!conn || !cliente) { fb.showError("Selecione um Cliente Corretamente!"); return; }
    if (!texto.trim()) { fb.showError("Digite o texto do contato."); return; }
    if (agendamento && agendamento < todayISO()) {
      fb.showError("A data de Agendamento não pode ser menor que a data atual!");
      return;
    }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/telemarketing/contato`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          cliente: cliente.codigo, texto: texto.trim(), agendamento: agendamento || null,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Histórico gravado.");
        setCliente((prev) => (prev ? { ...prev, historico: j.historico ?? prev.historico, ultimo_contato: todayISO() } : prev));
        limpar();
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  };

  const buscarSelecionar = async () => {
    if (!conn) return;
    setGridLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/telemarketing/selecionar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          dia_contato: fDiaContato, dia_entrega: fDiaEntrega, cliente_termo: fClienteTermo.trim() || null,
          vendedor: fVendedor, regiao: fRegiao, segmento: fSegmento, rota: fRota,
          tipo_cliente: fTipoCliente, situacao: fSituacao,
          cgc_cpf: fCgcCpf.trim() || null, bairro: fBairro.trim() || null,
          ultimo_contato_de: fUltContatoDe || null, ultimo_contato_ate: fUltContatoAte || null,
          agendamento_de: fAgendDe || null, agendamento_ate: fAgendAte || null,
          ordenar_por: fOrdenarPor,
        }),
      });
      const j = await r.json();
      setGridItems(j?.success ? j.items || [] : []);
      if (!j?.success) fb.showError(j?.message || "Falha ao consultar.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setGridLoading(false); }
  };

  const exportarPlanilha = () => {
    if (typeof window === "undefined") return;
    const header = ["Cliente", "Fantasia", "Contato", "Telefone", "Últ. Contato", "Dia Contato", "Dia Entrega", "Agendamento", "Usuário"];
    const linhas = gridItems.map((it) => [
      it.nome, it.fantasia, it.contato, it.telefone, isoToBR(it.ultimo_contato),
      it.dia_contato_nome || "", it.dia_entrega_nome || "", isoToBR(it.data_agendamento),
      it.funcionario_agendamento_nome || "",
    ]);
    const csv = [header, ...linhas].map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "telemarketing.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const canSave = can("TELEMARKETING.GRAVAR") || isMaster;
  const canWhatsapp = can("TELEMARKETING.WHATSAPP") || isMaster;
  const canExport = can("TELEMARKETING.EXPORTAR") || isMaster;

  // ============ View: Selecionar Clientes ============
  if (view === "selecionar") {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="telemarketing-selecionar-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setView("main")} hitSlop={12} style={styles.back}>
            <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
          <Text style={styles.headerTitle}>Selecionar Clientes</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShellWide}>
            <View style={styles.filterCard}>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Dia de Contato</Text>
                  <SelectField value={fDiaContato} onChange={(v) => setFDiaContato(v == null ? null : Number(v))} options={diaSemanaOpts} placeholder="Todos" allowClear compactWeb testID="f-dia-contato" modalTitle="Dia de Contato" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Dia de Entrega</Text>
                  <SelectField value={fDiaEntrega} onChange={(v) => setFDiaEntrega(v == null ? null : Number(v))} options={diaSemanaOpts} placeholder="Todos" allowClear compactWeb testID="f-dia-entrega" modalTitle="Dia de Entrega" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Cliente (parte do nome ou código)</Text>
                  <TextInput
                    value={fClienteTermo}
                    onChangeText={setFClienteTermo}
                    onSubmitEditing={buscarSelecionar}
                    onBlur={buscarSelecionar}
                    style={styles.input}
                    placeholderTextColor={colors.muted}
                    testID="f-cliente"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Vendedor</Text>
                  <SelectField value={fVendedor} onChange={(v) => setFVendedor(v == null ? null : Number(v))} options={funcionariosOpts} placeholder="Todos" allowClear compactWeb testID="f-vendedor" modalTitle="Vendedor" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Região</Text>
                  <SelectField value={fRegiao} onChange={(v) => setFRegiao(v == null ? null : Number(v))} options={regioesOpts} placeholder="Todas" allowClear compactWeb testID="f-regiao" modalTitle="Região" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Segmento</Text>
                  <SelectField value={fSegmento} onChange={(v) => setFSegmento(v == null ? null : String(v))} options={segmentosOpts} placeholder="Todos" allowClear compactWeb testID="f-segmento" modalTitle="Segmento" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Rota</Text>
                  <SelectField value={fRota} onChange={(v) => setFRota(v == null ? null : Number(v))} options={rotasOpts} placeholder="Todas" allowClear compactWeb testID="f-rota" modalTitle="Rota" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo Cliente</Text>
                  <SelectField value={fTipoCliente} onChange={(v) => setFTipoCliente(v == null ? null : Number(v))} options={tipoClienteOpts} placeholder="Todos" allowClear compactWeb testID="f-tipo-cliente" modalTitle="Tipo Cliente" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Bairro</Text>
                  <TextInput
                    value={fBairro}
                    onChangeText={setFBairro}
                    onSubmitEditing={buscarSelecionar}
                    onBlur={buscarSelecionar}
                    style={styles.input}
                    placeholderTextColor={colors.muted}
                    testID="f-bairro"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>CPF / CNPJ</Text>
                  <TextInput
                    value={fCgcCpf}
                    onChangeText={setFCgcCpf}
                    onSubmitEditing={buscarSelecionar}
                    onBlur={buscarSelecionar}
                    style={styles.input}
                    placeholderTextColor={colors.muted}
                    testID="f-cgc"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Situação</Text>
                  <SelectField value={fSituacao} onChange={(v) => setFSituacao(v == null ? null : String(v))} options={situacaoOpts} placeholder="Todas" allowClear compactWeb testID="f-situacao" modalTitle="Situação" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Últ. Contato de</Text>
                  <WebDateField value={fUltContatoDe} onChange={setFUltContatoDe} testID="tele-filtro-ult-contato-de" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                  <WebDateField value={fUltContatoAte} onChange={setFUltContatoAte} testID="tele-filtro-ult-contato-ate" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Agendamento de</Text>
                  <WebDateField value={fAgendDe} onChange={setFAgendDe} testID="tele-filtro-agend-de" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                  <WebDateField value={fAgendAte} onChange={setFAgendAte} testID="tele-filtro-agend-ate" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Ordenar Por</Text>
                  <View style={styles.tipoRow}>
                    <Pressable onPress={() => setFOrdenarPor("cliente")} style={[styles.tipoBtn, fOrdenarPor === "cliente" && styles.tipoBtnSel]}>
                      <Text style={[styles.tipoBtnText, fOrdenarPor === "cliente" && styles.tipoBtnTextSel]}>Cliente</Text>
                    </Pressable>
                    <Pressable onPress={() => setFOrdenarPor("ultimo_contato")} style={[styles.tipoBtn, fOrdenarPor === "ultimo_contato" && styles.tipoBtnSel]}>
                      <Text style={[styles.tipoBtnText, fOrdenarPor === "ultimo_contato" && styles.tipoBtnTextSel]}>Último Contato</Text>
                    </Pressable>
                  </View>
                </View>
                <Pressable onPress={buscarSelecionar} style={styles.searchBtn} testID="btn-selecionar">
                  <Ionicons name="search" size={18} color="#fff" />
                  <Text style={styles.searchBtnText}>Selecionar</Text>
                </Pressable>
                {canExport ? (
                  <Pressable onPress={exportarPlanilha} style={styles.exportBtn} testID="btn-gerar-planilha">
                    <Ionicons name="document-text-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.exportBtnText}>Gerar Planilha</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>

            {gridLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
            {!gridLoading && gridItems.length === 0 ? <Text style={styles.empty}>Nenhum cliente encontrado — ajuste os filtros e clique em Selecionar.</Text> : null}
            {gridItems.map((it) => (
              <Pressable key={it.codigo} onPress={() => carregarCliente(it.codigo)} style={styles.gridRow} testID={`sel-cliente-${it.codigo}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.gridNome}>{it.nome}{it.fantasia ? ` (${it.fantasia})` : ""}</Text>
                  <Text style={styles.gridSub}>
                    {it.contato || "sem contato"}{it.telefone ? ` · ${it.telefone}` : ""} · Últ. contato: {isoToBR(it.ultimo_contato)}
                  </Text>
                  {it.data_agendamento ? (
                    <Text style={styles.gridSub}>Agendamento: {isoToBR(it.data_agendamento)}{it.funcionario_agendamento_nome ? ` · ${it.funcionario_agendamento_nome}` : ""}</Text>
                  ) : null}
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ============ View: Principal (Dados do Cliente + Contato Atual + Histórico) ============
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="telemarketing-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Telemarketing</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView ref={mainScrollRef} contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShellWide}>
          <View style={styles.twoColRow}>
            {/* ---- Contato Atual + ações primeiro (evita rolar a tela pra
                anotar o contato) + Dados do Cliente logo abaixo ---- */}
            <View style={styles.leftCol}>
              <View style={styles.filterCard}>
                <Text style={styles.sectionTitle}>Contato Atual</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Data/Hora</Text>
                    <View style={styles.readonlyBox}><Text style={styles.readonlyText}>{timestamp || "-"}</Text></View>
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Agendamento</Text>
                    <WebDateField value={agendamento} onChange={(v) => setAgendamento(v || null)} testID="tele-agendamento" />
                  </View>
                </View>
                <TextInput
                  value={texto}
                  onChangeText={setTexto}
                  style={[styles.input, styles.inputMultiline]}
                  multiline
                  placeholder="Anotações do contato atual"
                  placeholderTextColor={colors.muted}
                  editable={!!cliente}
                  testID="telemarketing-texto"
                />
                <Pressable onPress={limpar} disabled={!cliente} style={[styles.secondaryBtn, !cliente && { opacity: 0.5 }]} testID="telemarketing-limpar">
                  <Text style={styles.secondaryBtnText}>Limpar</Text>
                </Pressable>
                <View style={styles.rowFields}>
                  {canSave ? (
                    <Pressable onPress={gravar} disabled={saving || !cliente} style={[styles.primaryBtn, { flex: 1 }, (saving || !cliente) && { opacity: 0.6 }]} testID="telemarketing-gravar">
                      {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                    </Pressable>
                  ) : null}
                  {canWhatsapp && cliente ? (
                    <WhatsappButton conn={conn} documentType="CLI" documentId={cliente.codigo} userId={auditCtx.usuario_alteracao} companyId={null} compact onStatusChange={setWaEnabled} />
                  ) : null}
                </View>
                {canWhatsapp && cliente && waEnabled === false ? (
                  <Text style={styles.waDisabledHint}>O envio por WhatsApp está desativado em Configurações.</Text>
                ) : null}
              </View>

              <View style={styles.actionsRow}>
                <Pressable onPress={() => setView("selecionar")} style={styles.actionBtn} testID="btn-selecionar-cliente">
                  <Ionicons name="search" size={18} color={colors.brandPrimary} />
                  <Text style={styles.actionBtnText}>Selecionar Cliente</Text>
                </Pressable>
                <Pressable
                  onPress={() => cliente && router.push({ pathname: "/cliente-completo", params: { codigo: String(cliente.codigo) } } as never)}
                  disabled={!cliente}
                  style={[styles.actionBtn, !cliente && { opacity: 0.5 }]}
                  testID="btn-alterar-cliente"
                >
                  <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                  <Text style={styles.actionBtnText}>Alterar Cliente</Text>
                </Pressable>
                <Pressable
                  onPress={() => cliente && router.push({ pathname: "/pedido-form", params: { cliente: String(cliente.codigo), cliente_nome: cliente.nome } } as never)}
                  disabled={!cliente}
                  style={[styles.actionBtn, !cliente && { opacity: 0.5 }]}
                  testID="btn-pedido-venda"
                >
                  <Ionicons name="cart-outline" size={18} color={colors.brandPrimary} />
                  <Text style={styles.actionBtnText}>Pedido de Venda</Text>
                </Pressable>
                <Pressable
                  onPress={() => cliente && router.push({ pathname: "/os-form", params: { cliente: String(cliente.codigo), cliente_nome: cliente.nome } } as never)}
                  disabled={!cliente}
                  style={[styles.actionBtn, !cliente && { opacity: 0.5 }]}
                  testID="btn-os"
                >
                  <Ionicons name="build-outline" size={18} color={colors.brandPrimary} />
                  <Text style={styles.actionBtnText}>O.S.</Text>
                </Pressable>
              </View>

              <View style={styles.filterCard}>
                <Text style={styles.sectionTitle}>Dados do Cliente</Text>
                {!cliente ? (
                  <Text style={styles.empty}>Nenhum cliente carregado — use "Selecionar Cliente".</Text>
                ) : (
                  <>
                    <InfoRow label="Nome" value={cliente.nome} />
                    <InfoRow label="Fantasia" value={cliente.fantasia} />
                    <View style={styles.rowFields}>
                      <InfoRow label="CNPJ/CPF" value={cliente.cgc_cpf} style={styles.colFlex} />
                      <InfoRow label="Data Cadastro" value={isoToBR(cliente.data_cadastro)} style={styles.colFlex} />
                    </View>
                    <InfoRow label="E-mail" value={cliente.e_mail} />
                    <View style={styles.rowFields}>
                      <InfoRow label="Telefone" value={cliente.telefone} style={styles.colFlex} />
                      <InfoRow label="Último Contato" value={isoToBR(cliente.ultimo_contato)} style={styles.colFlex} />
                    </View>
                    <InfoRow label="Contato" value={cliente.contato} />
                    <InfoRow label="Endereço" value={cliente.endereco} />
                    <View style={styles.rowFields}>
                      <InfoRow label="Rota" value={cliente.rota_nome || "-"} style={styles.colFlex} />
                      <InfoRow label="Região" value={cliente.regiao_nome || "-"} style={styles.colFlex} />
                    </View>
                    <View style={styles.rowFields}>
                      <InfoRow label="Segmento" value={cliente.segmento_nome || "-"} style={styles.colFlex} />
                      <InfoRow label="Tipo do Cliente" value={cliente.tipo_cliente_nome || "-"} style={styles.colFlex} />
                    </View>
                  </>
                )}
              </View>
            </View>

            {/* ---- Histórico ---- */}
            <View style={styles.rightCol}>
              <View style={[styles.filterCard, { flex: 1 }]}>
                <Text style={styles.sectionTitle}>Histórico</Text>
                <ScrollView style={styles.historicoScroll}>
                  <Text style={styles.historicoText} selectable>{cliente?.historico || "Sem histórico."}</Text>
                </ScrollView>
              </View>
            </View>
          </View>
        </View>
      </ScrollView>

      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => { setSearchOpen(false); carregarCliente(c.codigo); }}
        onCreate={() => { setSearchOpen(false); router.push({ pathname: "/cliente-form", params: { initial_nome: searchTerm } } as never); }}
      />
    </SafeAreaView>
  );
}

function InfoRow({ label, value, style }: { label: string; value: string; style?: object }) {
  return (
    <View style={style}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.readonlyBox}><Text style={styles.readonlyText} numberOfLines={2}>{value || "-"}</Text></View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShellWide: { width: "100%", maxWidth: 1200, alignSelf: "center" },
  scroll: { padding: spacing.lg, paddingBottom: 60 },
  scrollWeb: WEB_SCROLL_CENTER,
  twoColRow: { flexDirection: "row", gap: spacing.lg, alignItems: "flex-start" },
  leftCol: { flex: 1, gap: spacing.lg, minWidth: 360 },
  rightCol: { flex: 1, minWidth: 360, alignSelf: "stretch" },
  filterCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg, gap: spacing.sm,
  },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.brandPrimary, marginBottom: 4, textTransform: "uppercase" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  colFlex: { flex: 1, minWidth: 140 },
  colNarrow: { width: 150 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs, marginBottom: 4 },
  readonlyBox: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, minHeight: 40, justifyContent: "center" },
  readonlyText: { fontSize: 13, color: colors.onSurface },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputMultiline: { minHeight: 100, textAlignVertical: "top" },
  secondaryBtn: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingVertical: 13, paddingHorizontal: spacing.lg, alignItems: "center" },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "600", fontSize: 14 },
  waDisabledHint: { fontSize: 12, color: colors.muted, textAlign: "center", marginTop: 4 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 13, alignItems: "center" },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  actionBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.brandPrimary,
    borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, backgroundColor: colors.surface,
  },
  actionBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  historicoScroll: { maxHeight: 620 },
  historicoText: { fontSize: 12, color: colors.onSurface, lineHeight: 18 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8 },
  searchBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42 },
  searchBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  exportBtn: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42 },
  exportBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  tipoRow: { flexDirection: "row", gap: spacing.sm },
  tipoBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" },
  tipoBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  tipoBtnTextSel: { color: colors.onBrandPrimary },
  gridRow: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginTop: spacing.sm,
  },
  gridNome: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  gridSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
