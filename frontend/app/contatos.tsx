import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

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
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";

type Conn = Connection;

type Contato = {
  codigo: number;
  data: string | null;
  cliente: string;
  telefone: string;
  telefone_2: string;
  tipo_cliente: number | null;
  tipo_cliente_nome: string | null;
  contato: string;
  profissional: number | null;
  profissional_nome: string | null;
  data_prev: string | null;
  hora_prev: string | null;
  obs: string;
  e_mail: string;
  endereco: string;
  bairro: string;
  indicacao: string;
};

const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const isoToBR = (iso: string | null) => {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const nowHM = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

// Cadastros > Contatos (tabela `contatos`). Legado: FrmContatos.frm
// ("Cadastro de Contatos...") + FrmConsContatos.frm (consulta, sem fonte
// fornecida — filtros replicados a partir do screenshot). Tela única,
// combina cadastro + listagem/filtros num só lugar (mesmo padrão já usado
// em Fornecedores/Entrada-Saída de Caixa). Ver memória de projeto
// "Contatos" para o mapeamento completo e pendências (FrmConCli2 não
// fornecido, CHAMA2 inferido, Telefone_1 não implementado, edição via
// UPDATE em vez do delete+reinsert do legado).
export default function ContatosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contatos está disponível apenas no web."
        testID="contatos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Contato[]>([]);
  const [loading, setLoading] = useState(false);

  // Filtros — mesmos da tela de consulta legada (FrmConsContatos).
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [prevDe, setPrevDe] = useState("");
  const [prevAte, setPrevAte] = useState("");
  const [fCliente, setFCliente] = useState("");
  const [fContato, setFContato] = useState("");
  const [fTelefone, setFTelefone] = useState("");
  const [fTipoCliente, setFTipoCliente] = useState<number | null>(null);
  const [fProfissional, setFProfissional] = useState<number | null>(null);

  const [tipoClienteOpts, setTipoClienteOpts] = useState<SelectOption[]>([]);
  const [profissionalOpts, setProfissionalOpts] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Contato | null>(null);
  const [saving, setSaving] = useState(false);

  const [data, setData] = useState(todayISO());
  const [cliente, setCliente] = useState("");
  const [telefone, setTelefone] = useState("");
  const [telefone2, setTelefone2] = useState("");
  const [email, setEmail] = useState("");
  const [tipoCliente, setTipoCliente] = useState<number | null>(null);
  const [contato, setContato] = useState("");
  const [profissional, setProfissional] = useState<number | null>(null);
  const [dataPrev, setDataPrev] = useState<string | null>(null);
  const [horaPrev, setHoraPrev] = useState("");
  const [endereco, setEndereco] = useState("");
  const [bairro, setBairro] = useState("");
  const [indicacao, setIndicacao] = useState("");
  const [obs, setObs] = useState("");

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = new URLSearchParams({
        servidor: c.servidor, banco: c.banco,
        ...(dataDe ? { data_de: dataDe } : {}),
        ...(dataAte ? { data_ate: dataAte } : {}),
        ...(prevDe ? { prev_de: prevDe } : {}),
        ...(prevAte ? { prev_ate: prevAte } : {}),
        ...(fCliente.trim() ? { cliente: fCliente.trim() } : {}),
        ...(fContato.trim() ? { contato: fContato.trim() } : {}),
        ...(fTelefone.trim() ? { telefone: fTelefone.trim() } : {}),
        ...(fTipoCliente ? { tipo_cliente: String(fTipoCliente) } : {}),
        ...(fProfissional ? { profissional: String(fProfissional) } : {}),
      });
      const r = await fetch(`${base}/api/contatos?${qs.toString()}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataDe, dataAte, prevDe, prevAte, fCliente, fContato, fTelefone, fTipoCliente, fProfissional]);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const r = await fetch(`${base}/api/tipo-cliente-contato?${qs}`);
      const j = await r.json();
      if (j?.success) setTipoClienteOpts((j.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch { /* opcional */ }
    try {
      const r = await fetch(`${base}/api/funcionarios?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setProfissionalOpts((j.items || []).map((i: any) => ({ value: i.codigo, label: i.nome_guerra || i.nome })));
      }
    } catch { /* opcional */ }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c);
      loadLookups(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const consultar = () => { if (conn) load(conn); };

  const resetForm = () => {
    setEditing(null); setData(todayISO()); setCliente(""); setTelefone(""); setTelefone2("");
    setEmail(""); setTipoCliente(null); setContato(""); setProfissional(null);
    setDataPrev(null); setHoraPrev(""); setEndereco(""); setBairro(""); setIndicacao(""); setObs("");
  };

  const openNew = () => { resetForm(); setFormOpen(true); };
  const openEdit = (it: Contato) => {
    setEditing(it);
    setData(it.data || todayISO());
    setCliente(it.cliente);
    setTelefone(it.telefone);
    setTelefone2(it.telefone_2);
    setEmail(it.e_mail);
    setTipoCliente(it.tipo_cliente);
    setContato(it.contato);
    setProfissional(it.profissional);
    setDataPrev(it.data_prev);
    setHoraPrev((it.hora_prev || "").slice(0, 5));
    setEndereco(it.endereco);
    setBairro(it.bairro);
    setIndicacao(it.indicacao);
    setObs(it.obs || "");
    setFormOpen(true);
  };

  // Nova anotação datada — adaptação do GotFocus do legado (que reinseria uma
  // linha com data/hora TODA vez que o campo Observação ganhava foco). Em web
  // isso spamaria linhas repetidas (foco muda com muito mais frequência que
  // no VB6) — virou um botão explícito "Nova anotação" em vez de disparar no
  // foco. Ver PENDENCIAS.md.
  const novaAnotacao = () => {
    const linha = `${isoToBR(todayISO())} - ${nowHM()}h - `;
    setObs((prev) => (prev.trim() ? `${prev.trim()}\n${linha}` : linha));
  };

  const save = async () => {
    if (!conn) return;
    if (!data) { fb.showError("Defina a data corretamente."); return; }
    if (!cliente.trim()) { fb.showError("Defina o cliente corretamente."); return; }
    if (!tipoCliente) { fb.showError("Defina o tipo de cliente corretamente."); return; }
    if (!profissional) { fb.showError("Defina o profissional corretamente."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contatos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: editing?.codigo ?? null, data, cliente: cliente.trim(),
          telefone: telefone.trim() || null, telefone_2: telefone2.trim() || null,
          tipo_cliente: tipoCliente, contato: contato.trim() || null, profissional,
          data_prev: dataPrev || null, hora_prev: horaPrev ? `${horaPrev}:00` : null,
          obs: obs.trim() || null, e_mail: email.trim() || null,
          endereco: endereco.trim() || null, bairro: bairro.trim() || null, indicacao: indicacao.trim() || null,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Contato gravado."); setFormOpen(false); load(conn); }
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  };

  const remove = async (it: Contato) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contatos/${it.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // Buscar cliente (reaproveita /api/clientes/find/search + ClientSearchModal,
  // já usado em Pedido/O.S.) — `contatos.cliente` é texto livre no legado
  // (não FK), então só preenche o nome; se a busca não achar nada, oferece
  // cadastrar (abre /cliente-form). CHAMA2() do legado (auto-preencher
  // Telefone a partir do cliente) foi inferida: só preenche Telefone se
  // ainda estiver vazio — ver comentário no service.
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

  const cadastrarCliente = () => {
    if (!cliente.trim()) { fb.showError("Defina o cliente corretamente."); return; }
    // Pré-preenche só o nome — cliente-form.tsx não aceita ainda
    // initial_telefone/initial_email/initial_endereco/initial_bairro (ver
    // PENDENCIAS.md); usuário completa os demais campos manualmente.
    router.push({ pathname: "/cliente-form", params: { initial_nome: cliente.trim() } });
  };

  const exportarPlanilha = () => {
    if (typeof window === "undefined") return;
    const header = ["Cliente", "Data", "Telefone", "Tipo Cliente", "Contato", "Profissional", "Data Prevista", "Hora Prevista", "Observação"];
    const linhas = items.map((it) => [
      it.cliente, isoToBR(it.data), it.telefone, it.tipo_cliente_nome || "", it.contato,
      it.profissional_nome || "", isoToBR(it.data_prev), it.hora_prev || "", (it.obs || "").replace(/\n/g, " | "),
    ]);
    const csv = [header, ...linhas]
      .map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "contatos.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  // WhatsApp — link direto (wa.me), sem envio/mensagem template nem
  // histórico (diferente do WhatsappButton usado em Pedido/O.S., que manda
  // o PDF do documento e grava log de envio). Contato não é um documento —
  // aqui é só "abrir conversa com este número", pedido explícito do usuário.
  const abrirWhatsapp = (it: Contato) => {
    const numero = (it.telefone || it.telefone_2 || "").replace(/\D/g, "");
    if (!numero) { fb.showError("Este contato não tem telefone cadastrado."); return; }
    const comDdi = numero.length <= 11 ? `55${numero}` : numero;
    const url = `https://wa.me/${comDdi}`;
    if (typeof window !== "undefined") window.open(url, "_blank");
  };

  const imprimir = (it: Contato) => {
    if (typeof window === "undefined") return;
    const win = window.open("", "_blank", "width=480,height=650");
    if (!win) return;
    const linha = (label: string, valor: string) =>
      `<div style="display:flex;gap:8px;margin-bottom:4px;"><strong style="min-width:120px;">${label}</strong><span>${valor || "-"}</span></div>`;
    win.document.write(`<!DOCTYPE html><html><head><title>Contato #${it.codigo}</title><style>
      body{font-family:Arial,sans-serif;font-size:13px;padding:20px;}
      h2{font-size:15px;}
    </style></head><body>
      <h2>Contato #${it.codigo}</h2>
      ${linha("Data", isoToBR(it.data))}
      ${linha("Cliente", it.cliente)}
      ${linha("Telefone", it.telefone)}
      ${linha("Telefone 2", it.telefone_2)}
      ${linha("Email", it.e_mail)}
      ${linha("Tipo Cliente", it.tipo_cliente_nome || "")}
      ${linha("Contato", it.contato)}
      ${linha("Profissional", it.profissional_nome || "")}
      ${linha("Data Prevista", isoToBR(it.data_prev))}
      ${linha("Hora Prevista", it.hora_prev || "")}
      ${linha("Endereço", it.endereco)}
      ${linha("Bairro", it.bairro)}
      ${linha("Indicação", it.indicacao)}
      <div style="margin-top:10px;"><strong>Observação</strong><div style="white-space:pre-wrap;margin-top:4px;">${(it.obs || "").replace(/</g, "&lt;")}</div></div>
    </body></html>`);
    win.document.close();
    win.focus();
    win.print();
  };

  const canSave = can("CONTATOS.GRAVAR") || isMaster;
  const canDel = can("CONTATOS.EXCLUIR") || isMaster;
  const canPrint = can("CONTATOS.IMPRIMIR") || isMaster;
  const canExport = can("CONTATOS.EXPORTAR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contatos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Contatos</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <View style={styles.filterRow}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Período de</Text>
              <WebDateField value={dataDe} onChange={setDataDe} testID="contatos-filtro-periodo-de" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>até</Text>
              <WebDateField value={dataAte} onChange={setDataAte} testID="contatos-filtro-periodo-ate" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Previsão de</Text>
              <WebDateField value={prevDe} onChange={setPrevDe} testID="contatos-filtro-prev-de" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>até</Text>
              <WebDateField value={prevAte} onChange={setPrevAte} testID="contatos-filtro-prev-ate" />
            </View>
          </View>
          <View style={styles.filterRow}>
            <View style={styles.colFlex}>
              <Text style={styles.label}>Cliente</Text>
              <TextInput value={fCliente} onChangeText={setFCliente} style={styles.input} placeholder="Nome do cliente" placeholderTextColor={colors.muted} testID="filtro-cliente" />
            </View>
            <View style={styles.colFlex}>
              <Text style={styles.label}>Contato</Text>
              <TextInput value={fContato} onChangeText={setFContato} style={styles.input} placeholder="Nome do contato" placeholderTextColor={colors.muted} testID="filtro-contato" />
            </View>
            <View style={styles.colNarrowWide}>
              <Text style={styles.label}>Telefone</Text>
              <TextInput value={fTelefone} onChangeText={setFTelefone} style={styles.input} placeholder="Telefone" placeholderTextColor={colors.muted} testID="filtro-telefone" />
            </View>
          </View>
          <View style={styles.filterRow}>
            <View style={styles.colFlex}>
              <Text style={styles.label}>Tipo de Cliente</Text>
              <SelectField value={fTipoCliente} onChange={(v) => setFTipoCliente(v == null ? null : Number(v))} options={tipoClienteOpts} placeholder="Todos" allowClear compactWeb testID="filtro-tipo-cliente" modalTitle="Tipo de Cliente" />
            </View>
            <View style={styles.colFlex}>
              <Text style={styles.label}>Profissional</Text>
              <SelectField value={fProfissional} onChange={(v) => setFProfissional(v == null ? null : Number(v))} options={profissionalOpts} placeholder="Todos" allowClear compactWeb testID="filtro-profissional" modalTitle="Profissional" />
            </View>
            <Pressable onPress={consultar} style={styles.searchBtn} testID="consultar-contatos">
              <Ionicons name="search" size={18} color="#fff" />
              <Text style={styles.searchBtnText}>Consultar</Text>
            </Pressable>
            {canExport ? (
              <Pressable onPress={exportarPlanilha} style={styles.exportBtn} testID="gerar-planilha">
                <Ionicons name="document-text-outline" size={18} color={colors.brandPrimary} />
                <Text style={styles.exportBtnText}>Gerar Planilha</Text>
              </Pressable>
            ) : null}
          </View>
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum contato encontrado.</Text> : null}
          {items.map((it) => (
            <View key={it.codigo} style={styles.row} testID={`contato-${it.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <View style={styles.rowTop}>
                  <Text style={styles.rowCliente}>{it.cliente}</Text>
                  <Text style={styles.rowData}>{isoToBR(it.data)}</Text>
                </View>
                <Text style={styles.rowSub}>
                  {it.tipo_cliente_nome || "-"} · {it.contato || "sem contato"} · {it.profissional_nome || "-"}
                  {it.telefone ? ` · ${it.telefone}` : ""}
                </Text>
                {it.data_prev ? (
                  <Text style={styles.rowSub}>Previsão: {isoToBR(it.data_prev)}{it.hora_prev ? ` às ${it.hora_prev.slice(0, 5)}` : ""}</Text>
                ) : null}
              </Pressable>
              <View style={styles.rowActions}>
                {it.telefone || it.telefone_2 ? (
                  <Pressable onPress={() => abrirWhatsapp(it)} hitSlop={8} testID={`whatsapp-${it.codigo}`}>
                    <Ionicons name="logo-whatsapp" size={20} color="#25D366" />
                  </Pressable>
                ) : null}
                {canPrint ? (
                  <Pressable onPress={() => imprimir(it)} hitSlop={8} testID={`imprimir-${it.codigo}`}>
                    <Ionicons name="print-outline" size={20} color={colors.muted} />
                  </Pressable>
                ) : null}
                {canDel ? (
                  <Pressable onPress={() => remove(it)} hitSlop={8} testID={`excluir-${it.codigo}`}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="novo-contato">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <AppModal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editing ? `Contato #${editing.codigo}` : "Novo contato"}</Text>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data *</Text>
                  <WebDateField value={data} onChange={setData} testID="contato-data" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Cliente *</Text>
                  <View style={styles.inputWithBtnRow}>
                    <TextInput value={cliente} onChangeText={setCliente} style={[styles.input, { flex: 1, minWidth: 0 }]} placeholder="Nome do cliente/prospect" placeholderTextColor={colors.muted} testID="contato-cliente" />
                    <Pressable onPress={() => { setSearchTerm(cliente); setSearchOpen(true); }} style={styles.iconBtn} testID="buscar-cliente">
                      <Ionicons name="search" size={18} color={colors.brandPrimary} />
                    </Pressable>
                  </View>
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Telefone</Text>
                  <TextInput value={telefone} onChangeText={setTelefone} style={styles.input} placeholder="Telefone" placeholderTextColor={colors.muted} testID="contato-telefone" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Telefone 2</Text>
                  <TextInput value={telefone2} onChangeText={setTelefone2} style={styles.input} placeholder="Telefone 2" placeholderTextColor={colors.muted} testID="contato-telefone2" />
                </View>
              </View>

              <Text style={styles.label}>Email</Text>
              <TextInput value={email} onChangeText={setEmail} style={styles.input} placeholder="email@exemplo.com" placeholderTextColor={colors.muted} autoCapitalize="none" keyboardType="email-address" testID="contato-email" />

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo Cliente *</Text>
                  <SelectField value={tipoCliente} onChange={(v) => setTipoCliente(v == null ? null : Number(v))} options={tipoClienteOpts} placeholder="Selecione…" allowClear compactWeb testID="contato-tipo-cliente" modalTitle="Tipo Cliente" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Profissional *</Text>
                  <SelectField value={profissional} onChange={(v) => setProfissional(v == null ? null : Number(v))} options={profissionalOpts} placeholder="Selecione…" allowClear compactWeb testID="contato-profissional" modalTitle="Profissional" />
                </View>
              </View>

              <Text style={styles.label}>Contato</Text>
              <TextInput value={contato} onChangeText={setContato} style={styles.input} placeholder="Pessoa de contato" placeholderTextColor={colors.muted} testID="contato-contato" />

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Prevista</Text>
                  <WebDateField value={dataPrev} onChange={(v) => setDataPrev(v || null)} testID="contato-data-prevista" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Hora Prevista</Text>
                  <WebDateField type="time" value={horaPrev} onChange={setHoraPrev} testID="contato-hora-prevista" />
                </View>
              </View>

              <Text style={styles.label}>Endereço</Text>
              <TextInput value={endereco} onChangeText={setEndereco} style={styles.input} placeholder="Endereço" placeholderTextColor={colors.muted} testID="contato-endereco" />

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Bairro</Text>
                  <TextInput value={bairro} onChangeText={setBairro} style={styles.input} placeholder="Bairro" placeholderTextColor={colors.muted} testID="contato-bairro" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Indicação</Text>
                  <TextInput value={indicacao} onChangeText={setIndicacao} style={styles.input} placeholder="Indicação" placeholderTextColor={colors.muted} testID="contato-indicacao" />
                </View>
              </View>

              <View style={styles.obsHeaderRow}>
                <Text style={styles.label}>Observação</Text>
                <Pressable onPress={novaAnotacao} style={styles.novaAnotacaoBtn} testID="nova-anotacao">
                  <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.novaAnotacaoText}>Nova anotação</Text>
                </Pressable>
              </View>
              <TextInput
                value={obs}
                onChangeText={setObs}
                style={[styles.input, styles.inputMultiline]}
                multiline
                placeholder="Histórico de anotações do contato"
                placeholderTextColor={colors.muted}
                testID="contato-obs"
              />

              <Pressable onPress={cadastrarCliente} style={styles.secondaryBtn} testID="cadastrar-cliente">
                <Ionicons name="person-add-outline" size={18} color={colors.brandPrimary} />
                <Text style={styles.secondaryBtnText}>Cadastrar Cliente</Text>
              </Pressable>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="contato-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => {
          setCliente(c.nome);
          if (!telefone.trim() && c.telefone) setTelefone(c.telefone);
          setSearchOpen(false);
        }}
        onCreate={() => {
          setSearchOpen(false);
          router.push({ pathname: "/cliente-form", params: clienteSearchParams(searchTerm) });
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 900, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: spacing.sm, gap: spacing.sm },
  filterRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, flexWrap: "wrap" },
  colNarrow: { width: 150 },
  colNarrowWide: { width: 200 },
  colFlex: { flex: 1, minWidth: 160 },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  searchBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42 },
  searchBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  exportBtn: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 42 },
  exportBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  rowCliente: { fontSize: 14, fontWeight: "700", color: colors.onSurface, flex: 1 },
  rowData: { fontSize: 12, color: colors.muted },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowActions: { flexDirection: "row", gap: spacing.md },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%", maxWidth: Platform.OS === "web" ? 560 : undefined, maxHeight: "90%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputMultiline: { minHeight: 90, textAlignVertical: "top" },
  inputWithBtnRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  iconBtn: { width: 42, height: 42, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  obsHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  novaAnotacaoBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  novaAnotacaoText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  secondaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, marginTop: spacing.lg },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 14 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
