// Envio de Equipamentos para Terceiros — migração de `FrmManRet.frm`
// ("Envio de Equipamentos para Terceiros"). Tela própria, standalone
// (mesmo padrão do form original — MDI child independente, não uma aba
// dentro de O.S.), web-only, sem abas (exceção "compact single-view
// screens" do CLAUDE.md — o legado também não tem tabs). Ver
// PENDENCIAS.md > "Envio para Terceiros" pro rastreio completo de campos
// e regras de negócio.
//
// "Terceiro" é sempre um FORNECEDOR (fornecedor.codigo_int) — confirmado
// no código-fonte legado, não texto livre. Cliente/Fornecedor usam busca
// real (ClientSearchModal/FornecedorSearchModal), mesmo padrão `[GLOBAL]`
// de "Campos de Identidade Precisam de Mecanismo de Busca".
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, apiDelete, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR, parseNum, fmtMoney2 } from "@/src/utils/format";
import { styles as pedidoStyles } from "@/src/components/pedido/styles";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";

const isWeb = Platform.OS === "web";

type RetificaRow = {
  num: number; os: number | null;
  marca: string; marca_descricao: string; modelo: string; modelo_descricao: string;
  numero_de_serie: string; entrada: string | null; saida: string | null;
  valor: number; obs: string;
  fornecedor: number | null; fornecedor_nome: string;
  cliente: number | null; cliente_nome: string;
  aberto: boolean;
};

export default function EnvioTerceirosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const feedback = useFeedback();

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Envio para Terceiros está disponível apenas no web."
        testID="envio-terceiros-web-only"
      />
    );
  }

  if (!can("RETIFICA.ABRIR")) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <LockedView testID="envio-terceiros-locked" />
      </SafeAreaView>
    );
  }

  return <EnvioTerceirosInner router={router} feedback={feedback} can={can} />;
}

function EnvioTerceirosInner({
  router, feedback, can,
}: {
  router: ReturnType<typeof useRouter>;
  feedback: ReturnType<typeof useFeedback>;
  can: (p: string) => boolean;
}) {
  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number | null>(null);
  const [classe, setClasse] = useState<number | null>(null);

  const [items, setItems] = useState<RetificaRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [somenteAbertos, setSomenteAbertos] = useState(true);

  const [marcasList, setMarcasList] = useState<{ codigo: string; descricao: string }[]>([]);
  const [modelosList, setModelosList] = useState<{ codigo: string; descricao: string }[]>([]);

  // -------- form (Envio/Alterar) --------
  const [formOpen, setFormOpen] = useState(false);
  const [editNum, setEditNum] = useState<number | null>(null);
  const [fOs, setFOs] = useState("");
  const [fMarca, setFMarca] = useState<string | null>(null);
  const [fModelo, setFModelo] = useState<string | null>(null);
  const [fCliente, setFCliente] = useState<ClienteRow | null>(null);
  const [fFornecedor, setFFornecedor] = useState<FornecedorRow | null>(null);
  const [fNumSerie, setFNumSerie] = useState("");
  const [fEntrada, setFEntrada] = useState<string | null>(null);
  const [fValor, setFValor] = useState("0,00");
  const [fObs, setFObs] = useState("");
  const [saving, setSaving] = useState(false);

  const [clienteSearchOpen, setClienteSearchOpen] = useState(false);
  const [clienteSearchTerm, setClienteSearchTerm] = useState("");
  const [clienteSearchResults, setClienteSearchResults] = useState<ClienteRow[]>([]);
  const [clienteSearchLoading, setClienteSearchLoading] = useState(false);

  const [fornSearchOpen, setFornSearchOpen] = useState(false);
  const [fornSearchTerm, setFornSearchTerm] = useState("");
  const [fornSearchResults, setFornSearchResults] = useState<FornecedorRow[]>([]);
  const [fornSearchLoading, setFornSearchLoading] = useState(false);

  // -------- retorno --------
  const [retornoItem, setRetornoItem] = useState<RetificaRow | null>(null);
  const [retornoSaida, setRetornoSaida] = useState<string | null>(null);
  const [retornoValor, setRetornoValor] = useState("0,00");
  const [retornoSaving, setRetornoSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      const fid = func?.codigo_int ?? func?.codigo;
      setUsuarioCod(fid != null ? parseInt(String(fid), 10) : -2);
      const cl = (s?.usuario as { classe?: number } | undefined)?.classe;
      setClasse(cl ?? null);
      if (c) {
        apiGet(c, "/api/tabelas/marcas", { marca_produto: "false" })
          .then((j) => setMarcasList(j?.success ? j.items || [] : []))
          .catch(() => setMarcasList([]));
      }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/retifica", { search, somente_abertos: somenteAbertos });
      setItems(j?.success ? j.items || [] : []);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao carregar."));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, search, somenteAbertos]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    if (!conn || !fMarca) { setModelosList([]); return; }
    apiGet(conn, "/api/tabelas/modelos", { cod_marca: fMarca })
      .then((j) => setModelosList(j?.success ? j.items || [] : []))
      .catch(() => setModelosList([]));
  }, [conn, fMarca]);

  useEffect(() => {
    if (!clienteSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setClienteSearchLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term: clienteSearchTerm });
        setClienteSearchResults(j?.items || []);
      } catch {
        setClienteSearchResults([]);
      } finally {
        setClienteSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [clienteSearchTerm, clienteSearchOpen, conn]);

  useEffect(() => {
    if (!fornSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setFornSearchLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(fornSearchTerm)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setFornSearchResults(j?.success ? j.items || [] : []);
      } catch {
        setFornSearchResults([]);
      } finally {
        setFornSearchLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [fornSearchTerm, fornSearchOpen, conn]);

  const resetForm = () => {
    setEditNum(null);
    setFOs(""); setFMarca(null); setFModelo(null); setFCliente(null); setFFornecedor(null);
    setFNumSerie(""); setFEntrada(null); setFValor("0,00"); setFObs("");
  };

  const openNovo = () => {
    resetForm();
    setFormOpen(true);
  };

  const openEdit = (item: RetificaRow) => {
    setEditNum(item.num);
    setFOs(item.os != null ? String(item.os) : "");
    setFMarca(item.marca || null);
    setFModelo(item.modelo || null);
    setFCliente(item.cliente ? { codigo: item.cliente, nome: item.cliente_nome, cgc_cpf: "", telefone: "" } : null);
    setFFornecedor(
      item.fornecedor
        ? { codigo_int: String(item.fornecedor), codigo: String(item.fornecedor), nome: item.fornecedor_nome }
        : null
    );
    setFNumSerie(item.numero_de_serie || "");
    setFEntrada(item.entrada);
    setFValor(item.valor > 0 ? fmtMoney2(item.valor) : "0,00");
    setFObs(item.obs || "");
    setFormOpen(true);
  };

  const handleSalvar = async () => {
    if (!conn) return;
    const osNum = parseInt(fOs, 10);
    if (!osNum) { feedback.showError("Informe o número da O.S."); return; }
    if (!fCliente) { feedback.showError("Selecione o cliente."); return; }
    if (!fFornecedor) { feedback.showError("Selecione o Terceiro (fornecedor)."); return; }
    if (!fNumSerie.trim()) { feedback.showError("Preencha o Número de Série."); return; }
    if (!fEntrada) { feedback.showError("Preencha a data de envio."); return; }
    setSaving(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        os: osNum, marca: fMarca || "", modelo: fModelo || "",
        cliente: fCliente.codigo, fornecedor: Number(fFornecedor.codigo_int),
        numero_de_serie: fNumSerie.trim(), entrada: fEntrada, valor: parseNum(fValor), obs: fObs,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      };
      const j = editNum
        ? await apiSend(conn, `/api/retifica/${editNum}`, "PUT", body)
        : await apiSend(conn, "/api/retifica", "POST", body);
      if (!j?.success) {
        feedback.showError(friendlyApiError(j, "Falha ao gravar."));
      } else {
        feedback.showSuccess(editNum ? "Registro atualizado." : `Envio nº ${j.num} registrado.`);
        setFormOpen(false);
        load();
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gravar."));
    } finally {
      setSaving(false);
    }
  };

  const openRetorno = (item: RetificaRow) => {
    setRetornoItem(item);
    setRetornoSaida(item.saida);
    setRetornoValor(item.valor > 0 ? fmtMoney2(item.valor) : "0,00");
  };

  const handleRetorno = async () => {
    if (!conn || !retornoItem) return;
    if (!retornoSaida) { feedback.showError("Preencha a data de retorno."); return; }
    setRetornoSaving(true);
    try {
      const j = await apiSend(conn, `/api/retifica/${retornoItem.num}/retorno`, "POST", {
        servidor: conn.servidor, banco: conn.banco,
        saida: retornoSaida, valor: parseNum(retornoValor),
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) {
        feedback.showError(friendlyApiError(j, "Falha ao gravar retorno."));
      } else {
        feedback.showSuccess("Retorno registrado.");
        setRetornoItem(null);
        load();
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gravar retorno."));
    } finally {
      setRetornoSaving(false);
    }
  };

  const handleExcluir = (item: RetificaRow) => {
    if (!conn) return;
    feedback.showConfirm(`Excluir o protocolo nº ${item.num}? Esta ação não pode ser desfeita.`, async () => {
      try {
        const j = await apiDelete(conn, `/api/retifica/${item.num}`, {
          usuario_alteracao: usuarioCod ?? undefined, classe: classe ?? undefined, plataforma: Platform.OS,
        });
        if (!j?.success) {
          feedback.showError(friendlyApiError(j, "Falha ao excluir."));
        } else {
          feedback.showSuccess("Protocolo excluído.");
          load();
        }
      } catch (e) {
        feedback.showError(friendlyCatchError(e, "Falha ao excluir."));
      }
    });
  };

  const marcaOptions: SelectOption[] = marcasList.map((m) => ({ value: m.codigo, label: m.descricao }));
  const modeloOptions: SelectOption[] = modelosList.map((m) => ({ value: m.codigo, label: m.descricao }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="envio-terceiros-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12} testID="envio-terceiros-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>Envio para Terceiros</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scrollWeb} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={search}
                onChangeText={setSearch}
                placeholder="Buscar por O.S., nº de série, cliente ou terceiro…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="envio-terceiros-search"
              />
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.sm }}>
              <TouchableOpacity
                onPress={() => setSomenteAbertos((v) => !v)}
                style={{ flexDirection: "row", alignItems: "center", gap: 6 }}
                testID="envio-terceiros-somente-abertos"
              >
                <Ionicons name={somenteAbertos ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={{ fontSize: 13, color: colors.onSurface }}>Somente em aberto (ainda não retornados)</Text>
              </TouchableOpacity>
              {can("RETIFICA.GRAVAR") ? (
                <Pressable onPress={openNovo} style={styles.novoBtn} testID="envio-terceiros-novo">
                  <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
                  <Text style={styles.novoBtnText}>Envio p/ Terceiro</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}

          <View style={{ gap: spacing.sm }}>
            {items.map((item) => (
              <View key={item.num} style={styles.row} testID={`envio-terceiros-${item.num}`}>
                <Pressable style={{ flex: 1 }} onPress={() => openEdit(item)}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <Text style={styles.rowTitle}>Protocolo nº {item.num} · O.S. {item.os}</Text>
                    <View style={[styles.sitTag, item.aberto ? styles.sitTagAberto : styles.sitTagFechado]}>
                      <Text style={[styles.sitTagText, { color: item.aberto ? colors.warning : colors.success }]}>
                        {item.aberto ? "Em aberto" : "Retornado"}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {item.cliente_nome || "(sem cliente)"} · Terceiro: {item.fornecedor_nome || "—"}
                  </Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    Nº Série: {item.numero_de_serie}
                    {item.marca_descricao ? ` · ${item.marca_descricao}` : ""}
                    {item.modelo_descricao ? ` ${item.modelo_descricao}` : ""}
                  </Text>
                  <Text style={styles.rowSub}>
                    Envio: {item.entrada ? formatDateBR(item.entrada) : "—"}
                    {item.saida ? ` · Retorno: ${formatDateBR(item.saida)}` : ""}
                    {item.valor > 0 ? ` · ${formatBRL(item.valor)}` : ""}
                  </Text>
                </Pressable>
                <View style={{ gap: 6 }}>
                  {item.aberto && can("RETIFICA.RETORNO") ? (
                    <TouchableOpacity onPress={() => openRetorno(item)} style={styles.actionBtn} testID={`envio-terceiros-retorno-${item.num}`}>
                      <Ionicons name="return-down-back-outline" size={14} color={colors.onBrandPrimary} />
                      <Text style={styles.actionBtnText}>Retorno</Text>
                    </TouchableOpacity>
                  ) : null}
                  {can("RETIFICA.EXCLUIR") ? (
                    <TouchableOpacity onPress={() => handleExcluir(item)} style={styles.deleteBtn} testID={`envio-terceiros-excluir-${item.num}`}>
                      <Ionicons name="trash-outline" size={14} color={colors.error} />
                    </TouchableOpacity>
                  ) : null}
                </View>
              </View>
            ))}
            {!loading && items.length === 0 ? (
              <Text style={styles.empty}>Nenhum protocolo encontrado.</Text>
            ) : null}
          </View>
          <View style={{ height: 40 }} />
        </View>
      </ScrollView>

      {/* Modal Envio/Alterar */}
      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setFormOpen(false)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>{editNum ? `Editar Protocolo nº ${editNum}` : "Envio p/ Terceiro"}</Text>
              <Pressable onPress={() => setFormOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: spacing.sm }}>
                <View style={pedidoStyles.dateRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Nº da O.S.</Text>
                    <TextInput
                      value={fOs}
                      onChangeText={setFOs}
                      keyboardType="number-pad"
                      placeholder="Número da O.S."
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="envio-terceiros-os"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Nº de Série</Text>
                    <TextInput
                      value={fNumSerie}
                      onChangeText={setFNumSerie}
                      placeholder="Número de série do equipamento"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="envio-terceiros-numserie"
                    />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>Cliente</Text>
                <Pressable
                  onPress={() => { setClienteSearchTerm(""); setClienteSearchResults([]); setClienteSearchOpen(true); }}
                  style={styles.selectBox}
                  testID="envio-terceiros-cliente"
                >
                  <Ionicons name="person-outline" size={16} color={colors.muted} />
                  <Text style={[styles.selectText, !fCliente && { color: colors.muted }]} numberOfLines={1}>
                    {fCliente ? fCliente.nome : "Buscar cliente"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <Text style={styles.fieldLabel}>Terceiro (Fornecedor)</Text>
                <Pressable
                  onPress={() => { setFornSearchTerm(""); setFornSearchResults([]); setFornSearchOpen(true); }}
                  style={styles.selectBox}
                  testID="envio-terceiros-fornecedor"
                >
                  <Ionicons name="business-outline" size={16} color={colors.muted} />
                  <Text style={[styles.selectText, !fFornecedor && { color: colors.muted }]} numberOfLines={1}>
                    {fFornecedor ? (fFornecedor.fantasia || fFornecedor.nome) : "Buscar fornecedor"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <View style={pedidoStyles.dateRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Marca</Text>
                    <SelectField
                      value={fMarca}
                      onChange={(v) => { setFMarca(v == null ? null : String(v)); setFModelo(null); }}
                      options={marcaOptions}
                      placeholder="Marca"
                      allowClear
                      compactWeb
                      modalTitle="Selecionar Marca"
                      testID="envio-terceiros-marca"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Modelo</Text>
                    <SelectField
                      value={fModelo}
                      onChange={(v) => setFModelo(v == null ? null : String(v))}
                      options={modeloOptions}
                      placeholder="Modelo"
                      allowClear
                      compactWeb
                      disabled={!fMarca}
                      modalTitle="Selecionar Modelo"
                      testID="envio-terceiros-modelo"
                    />
                  </View>
                </View>

                <View style={pedidoStyles.dateRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Data de Envio</Text>
                    <WebDateField value={fEntrada} onChange={setFEntrada} testID="envio-terceiros-entrada" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor</Text>
                    <TextInput
                      value={fValor}
                      onChangeText={setFValor}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="envio-terceiros-valor"
                    />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>Observações</Text>
                <TextInput
                  value={fObs}
                  onChangeText={setFObs}
                  placeholder="Observações (defeito relatado, condição do equipamento, etc.)"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
                  multiline
                  testID="envio-terceiros-obs"
                />

                <View style={pedidoStyles.modalBtns}>
                  <Pressable onPress={() => setFormOpen(false)} style={[pedidoStyles.secondaryBtn, { flex: 1, alignItems: "center" }]}>
                    <Text style={pedidoStyles.secondaryBtnText}>Cancelar</Text>
                  </Pressable>
                  {can("RETIFICA.GRAVAR") ? (
                    <Pressable
                      onPress={handleSalvar}
                      disabled={saving}
                      style={[pedidoStyles.primaryBtn, { flex: 1 }, saving && { opacity: 0.7 }]}
                      testID="envio-terceiros-salvar"
                    >
                      {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={pedidoStyles.primaryBtnText}>Gravar</Text>}
                    </Pressable>
                  ) : null}
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal Retorno */}
      <Modal visible={!!retornoItem} transparent animationType="slide" onRequestClose={() => setRetornoItem(null)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setRetornoItem(null)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Retorno do Terceiro</Text>
              <Pressable onPress={() => setRetornoItem(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {retornoItem ? (
              <View style={{ gap: spacing.sm }}>
                <Text style={styles.rowSub}>
                  Protocolo nº {retornoItem.num} · O.S. {retornoItem.os} · Nº Série: {retornoItem.numero_de_serie}
                </Text>
                <Text style={styles.fieldLabel}>Data de Retorno</Text>
                <WebDateField value={retornoSaida} onChange={setRetornoSaida} testID="envio-terceiros-retorno-data" />
                <Text style={styles.fieldLabel}>Valor Cobrado</Text>
                <TextInput
                  value={retornoValor}
                  onChangeText={setRetornoValor}
                  keyboardType="decimal-pad"
                  placeholder="0,00"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="envio-terceiros-retorno-valor"
                />
                <Pressable
                  onPress={handleRetorno}
                  disabled={retornoSaving}
                  style={[pedidoStyles.primaryBtn, retornoSaving && { opacity: 0.7 }]}
                  testID="envio-terceiros-retorno-confirmar"
                >
                  {retornoSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={pedidoStyles.primaryBtnText}>Confirmar Retorno</Text>}
                </Pressable>
              </View>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      <ClientSearchModal
        visible={clienteSearchOpen}
        onClose={() => setClienteSearchOpen(false)}
        term={clienteSearchTerm}
        setTerm={setClienteSearchTerm}
        loading={clienteSearchLoading}
        results={clienteSearchResults}
        onPick={(c) => { setFCliente(c); setClienteSearchOpen(false); }}
        onCreate={() => setClienteSearchOpen(false)}
      />
      <FornecedorSearchModal
        visible={fornSearchOpen}
        onClose={() => setFornSearchOpen(false)}
        term={fornSearchTerm}
        setTerm={setFornSearchTerm}
        loading={fornSearchLoading}
        results={fornSearchResults}
        onPick={(f) => { setFFornecedor(f); setFornSearchOpen(false); }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginTop: spacing.md, marginBottom: spacing.md },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10,
  },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface, minWidth: 0 },
  novoBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary,
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8, marginLeft: "auto",
  },
  novoBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  row: {
    flexDirection: "row", alignItems: "flex-start", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.sm },
  sitTagAberto: { backgroundColor: "#fff4e0" },
  sitTagFechado: { backgroundColor: "#DCFCE7" },
  sitTagText: { fontSize: 10, fontWeight: "700" },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  actionBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary,
    borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6,
  },
  actionBtnText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "600" },
  deleteBtn: {
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.error,
    borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6,
  },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
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
});
