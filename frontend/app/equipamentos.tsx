import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
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

type Conn = Connection;
type Tipo = "A" | "C";

type Equipamento = {
  codigo: number;
  cliente: number;
  numero_de_serie: string;
  numero_de_serie_int: string;
  marca: string;
  marca_descricao: string | null;
  modelo: string;
  modelo_descricao: string | null;
  portador: string;
  local: string;
  tipo_equipamento: Tipo;
  detalhe_equipamento: string;
  situacao_equipamento: "A" | "D";
  descricao_equipamento: string;
  valor: number;
  revisao: string | null;
};

const isoToBR = (iso: string | null) => {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const fmtMoney = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;

// Cadastros > Equipamentos (tabela `equipamentos`). Legado: FrmManEquip.frm
// ("Manutenção de Equipamentos.") — todo equipamento pertence a um cliente
// (pedido explícito do usuário), então a tela sempre parte da seleção de um
// cliente antes de listar/gerenciar. Ver memória de projeto "Equipamentos"
// pro mapeamento completo e pendências (Pos_Sistema não implementado,
// cascata de Alterar Núm. Série não toca os.chassi, impressão simplificada).
export default function EquipamentosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Equipamentos está disponível apenas no web."
        testID="equipamentos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [items, setItems] = useState<Equipamento[]>([]);
  const [loading, setLoading] = useState(false);

  const [busca, setBusca] = useState("");
  const [fTipo, setFTipo] = useState<Tipo | null>(null);
  const [fSituacao, setFSituacao] = useState<"A" | "D" | null>(null);

  const [clienteSearchOpen, setClienteSearchOpen] = useState(false);
  const [clienteSearchTerm, setClienteSearchTerm] = useState("");
  const [clienteSearchLoading, setClienteSearchLoading] = useState(false);
  const [clienteSearchResults, setClienteSearchResults] = useState<ClienteRow[]>([]);

  const [marcasOpts, setMarcasOpts] = useState<SelectOption[]>([]);
  const [modelosOpts, setModelosOpts] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Equipamento | null>(null);
  const [saving, setSaving] = useState(false);

  const [numeroSerie, setNumeroSerie] = useState("");
  const [numeroSerieInt, setNumeroSerieInt] = useState("");
  const [marca, setMarca] = useState<string | null>(null);
  const [modelo, setModelo] = useState<string | null>(null);
  const [portador, setPortador] = useState("");
  const [local, setLocal] = useState("");
  const [revisao, setRevisao] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [tipoEquipamento, setTipoEquipamento] = useState<Tipo>("A");
  const [ativo, setAtivo] = useState(true);
  const [detalhe, setDetalhe] = useState("");

  const [altSerieOpen, setAltSerieOpen] = useState(false);
  const [altSerieCodigo, setAltSerieCodigo] = useState<number | null>(null);
  const [altSerieNovo, setAltSerieNovo] = useState("");
  const [altSerieSaving, setAltSerieSaving] = useState(false);

  const load = useCallback(async (c: Conn, cli: number) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = new URLSearchParams({
        servidor: c.servidor, banco: c.banco, cliente: String(cli),
        ...(busca.trim() ? { busca: busca.trim() } : {}),
        ...(fTipo ? { tipo: fTipo } : {}),
        ...(fSituacao ? { situacao: fSituacao } : {}),
      });
      const r = await fetch(`${base}/api/equipamentos?${qs.toString()}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca, fTipo, fSituacao]);

  const loadMarcas = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/marcas?${qs}`);
      const j = await r.json();
      if (j?.success) setMarcasOpts((j.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch { /* opcional */ }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      loadMarcas(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (conn && cliente) load(conn, cliente.codigo);
  }, [conn, cliente, load]);

  useEffect(() => {
    if (!conn || !marca) { setModelosOpts([]); return; }
    (async () => {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&cod_marca=${encodeURIComponent(marca)}`;
      try {
        const r = await fetch(`${base}/api/tabelas/modelos?${qs}`);
        const j = await r.json();
        setModelosOpts(j?.success ? (j.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })) : []);
      } catch { setModelosOpts([]); }
    })();
  }, [conn, marca]);

  // Busca de cliente — reaproveita ClientSearchModal (mesmo padrão de
  // Pedido/O.S./Contatos). Diferente de Contatos, aqui `equipamentos.cliente`
  // é sempre um código real (não texto livre) — obrigatório antes de
  // listar/incluir qualquer equipamento.
  useEffect(() => {
    if (!clienteSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setClienteSearchLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(clienteSearchTerm)}`;
        const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
        const j = await r.json();
        setClienteSearchResults(j?.items || []);
      } catch { setClienteSearchResults([]); } finally { setClienteSearchLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [clienteSearchTerm, clienteSearchOpen, conn]);

  const resetForm = () => {
    setEditing(null); setNumeroSerie(""); setNumeroSerieInt(""); setMarca(null); setModelo(null);
    setPortador(""); setLocal(""); setRevisao(null); setDescricao(""); setValor("");
    setTipoEquipamento("A"); setAtivo(true); setDetalhe("");
  };

  const openNew = () => { resetForm(); setFormOpen(true); };
  const openEdit = (it: Equipamento) => {
    setEditing(it);
    setNumeroSerie(it.numero_de_serie);
    setNumeroSerieInt(it.numero_de_serie_int);
    setMarca(it.marca || null);
    setModelo(it.modelo || null);
    setPortador(it.portador);
    setLocal(it.local);
    setRevisao(it.revisao);
    setDescricao(it.descricao_equipamento);
    setValor(it.valor ? String(it.valor).replace(".", ",") : "");
    setTipoEquipamento(it.tipo_equipamento);
    setAtivo(it.situacao_equipamento !== "D");
    setDetalhe(it.detalhe_equipamento || "");
    setFormOpen(true);
  };

  // Sugerir Descrição a partir de Marca/Modelo — adaptação do legado
  // (Campo_GotFocus sobrescrevia SEMPRE, a cada foco, mesmo texto já
  // digitado — vira ação explícita aqui, ver PENDENCIAS.md).
  const sugerirDescricao = () => {
    const m = marcasOpts.find((o) => o.value === marca)?.label || "";
    const mo = modelosOpts.find((o) => o.value === modelo)?.label || "";
    const sugestao = `${mo} ${m}`.trim().slice(0, 50);
    if (sugestao) setDescricao(sugestao);
  };

  const save = async () => {
    if (!conn || !cliente) return;
    if (!numeroSerie.trim()) { fb.showError("Insira o Número de Série."); return; }
    if (!marca) { fb.showError("Defina a Marca."); return; }
    if (!modelo) { fb.showError("Defina o Modelo."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/equipamentos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: editing?.codigo ?? null, cliente: cliente.codigo,
          numero_de_serie: numeroSerie.trim(), numero_de_serie_int: numeroSerieInt.trim() || null,
          marca, modelo, portador: portador.trim() || null, local: local.trim() || null,
          tipo_equipamento: tipoEquipamento, detalhe_equipamento: detalhe.trim() || null,
          situacao_equipamento: ativo ? "A" : "D",
          descricao_equipamento: descricao.trim() || null,
          valor: valor ? parseFloat(valor.replace(/\./g, "").replace(",", ".")) : 0,
          revisao: revisao || null,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Equipamento gravado."); setFormOpen(false); load(conn, cliente.codigo); }
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  };

  const remove = async (it: Equipamento) => {
    if (!conn || !cliente) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/equipamentos/${it.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn, cliente.codigo); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const disponibilizar = async (it: Equipamento) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/equipamentos/${it.codigo}/disponibilizar-contrato`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) fb.showSuccess(j.message || "Disponibilizado.");
      else fb.showError(j?.message || "Falha.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const abrirAlterarSerie = (it: Equipamento) => {
    setAltSerieCodigo(it.codigo);
    setAltSerieNovo(it.numero_de_serie);
    setAltSerieOpen(true);
  };
  const confirmarAlterarSerie = async () => {
    if (!conn || !cliente || altSerieCodigo == null) return;
    if (!altSerieNovo.trim()) { fb.showError("Defina o novo Número de Série."); return; }
    setAltSerieSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/equipamentos/${altSerieCodigo}/alterar-numero-serie`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, novo_numero_de_serie: altSerieNovo.trim() }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Alterado."); setAltSerieOpen(false); load(conn, cliente.codigo); }
      else fb.showError(j?.message || "Falha ao alterar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setAltSerieSaving(false); }
  };

  const imprimir = () => {
    if (typeof window === "undefined" || !cliente) return;
    const win = window.open("", "_blank", "width=900,height=650");
    if (!win) return;
    const linhas = items.map((it) => `<tr>
      <td>${it.numero_de_serie}</td><td>${it.numero_de_serie_int}</td>
      <td>${it.marca_descricao || it.marca}</td><td>${it.modelo_descricao || it.modelo}</td>
      <td>${it.portador}</td><td>${it.local}</td>
      <td>${it.tipo_equipamento === "A" ? "Avulso" : "Contrato"}</td>
      <td>${(it.detalhe_equipamento || "").replace(/</g, "&lt;")}</td>
    </tr>`).join("");
    win.document.write(`<!DOCTYPE html><html><head><title>Equipamentos - ${cliente.nome}</title><style>
      body{font-family:Arial,sans-serif;font-size:11px;padding:16px;}
      table{width:100%;border-collapse:collapse;} th,td{border:1px solid #999;padding:4px;text-align:left;}
      th{background:#eee;}
      h2{font-size:14px;}
    </style></head><body>
      <h2>Equipamentos — ${cliente.nome}</h2>
      <table><thead><tr>
        <th>Nº Série</th><th>Nº Série Interno</th><th>Marca</th><th>Modelo</th>
        <th>Usuário</th><th>Local</th><th>Tipo</th><th>Detalhes</th>
      </tr></thead><tbody>${linhas}</tbody></table>
    </body></html>`);
    win.document.close();
    win.focus();
    win.print();
  };

  const canSave = can("EQUIPAMENTOS.GRAVAR") || isMaster;
  const canDel = can("EQUIPAMENTOS.EXCLUIR") || isMaster;
  const canPrint = can("EQUIPAMENTOS.IMPRIMIR") || isMaster;
  const canAlterarTipo = can("EQUIPAMENTOS.ALTERAR_TIPO") || isMaster;
  const canDisponibilizar = can("EQUIPAMENTOS.DISPONIBILIZAR") || isMaster;
  const canAltSerie = can("EQUIPAMENTOS.ALT_NUM_SERIE") || isMaster;

  const tipoFiltroOpts: SelectOption[] = [{ value: "A", label: "Avulso" }, { value: "C", label: "Contrato" }];
  const situacaoFiltroOpts: SelectOption[] = [{ value: "A", label: "Ativo" }, { value: "D", label: "Desativado" }];

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="equipamentos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Equipamentos</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.clienteBox}>
          {cliente ? (
            <View style={styles.clienteRow}>
              <Ionicons name="person-circle-outline" size={22} color={colors.brandPrimary} />
              <Text style={styles.clienteNome} numberOfLines={1}>{cliente.nome}</Text>
              <Pressable onPress={() => { setClienteSearchTerm(""); setClienteSearchOpen(true); }} testID="trocar-cliente">
                <Text style={styles.trocarText}>Trocar</Text>
              </Pressable>
            </View>
          ) : (
            <Pressable onPress={() => { setClienteSearchTerm(""); setClienteSearchOpen(true); }} style={styles.selecionarClienteBtn} testID="selecionar-cliente">
              <Ionicons name="search" size={18} color="#fff" />
              <Text style={styles.selecionarClienteText}>Selecionar Cliente</Text>
            </Pressable>
          )}
        </View>

        {cliente ? (
          <>
            <View style={styles.filterBox}>
              <View style={styles.filterRow}>
                <View style={styles.colFlex}>
                  <TextInput value={busca} onChangeText={setBusca} style={styles.input} placeholder="Buscar por nº série, descrição, usuário ou local…" placeholderTextColor={colors.muted} testID="filtro-busca" />
                </View>
                <View style={styles.colNarrow}>
                  <SelectField value={fTipo} onChange={(v) => setFTipo(v == null ? null : (v as Tipo))} options={tipoFiltroOpts} placeholder="Todos os tipos" allowClear compactWeb testID="filtro-tipo" modalTitle="Tipo" />
                </View>
                <View style={styles.colNarrow}>
                  <SelectField value={fSituacao} onChange={(v) => setFSituacao(v == null ? null : (v as "A" | "D"))} options={situacaoFiltroOpts} placeholder="Todas situações" allowClear compactWeb testID="filtro-situacao" modalTitle="Situação" />
                </View>
                {canPrint ? (
                  <Pressable onPress={imprimir} style={styles.exportBtn} testID="imprimir-lista">
                    <Ionicons name="print-outline" size={18} color={colors.brandPrimary} />
                  </Pressable>
                ) : null}
              </View>
            </View>

            <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
              {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
              {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum equipamento cadastrado para este cliente.</Text> : null}
              {items.map((it) => (
                <View key={it.codigo} style={styles.row} testID={`equipamento-${it.codigo}`}>
                  <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                    <View style={styles.rowTop}>
                      <Text style={styles.rowSerie}>{it.numero_de_serie}</Text>
                      <View style={[styles.badge, it.tipo_equipamento === "C" ? styles.badgeContrato : styles.badgeAvulso]}>
                        <Text style={styles.badgeText}>{it.tipo_equipamento === "C" ? "Contrato" : "Avulso"}</Text>
                      </View>
                      {it.situacao_equipamento === "D" ? (
                        <View style={styles.badgeInativo}><Text style={styles.badgeText}>Desativado</Text></View>
                      ) : null}
                    </View>
                    <Text style={styles.rowDesc}>{it.descricao_equipamento || `${it.marca_descricao || ""} ${it.modelo_descricao || ""}`.trim()}</Text>
                    <Text style={styles.rowSub}>{it.marca_descricao || it.marca} · {it.modelo_descricao || it.modelo} · Usuário: {it.portador || "-"} · Local: {it.local || "-"}</Text>
                  </Pressable>
                  <View style={styles.rowActions}>
                    {canDisponibilizar ? (
                      <Pressable onPress={() => disponibilizar(it)} hitSlop={8} testID={`disponibilizar-${it.codigo}`}>
                        <Ionicons name="briefcase-outline" size={20} color={colors.muted} />
                      </Pressable>
                    ) : null}
                    {canAltSerie ? (
                      <Pressable onPress={() => abrirAlterarSerie(it)} hitSlop={8} testID={`alt-serie-${it.codigo}`}>
                        <Ionicons name="barcode-outline" size={20} color={colors.muted} />
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
          </>
        ) : (
          <View style={styles.emptyClienteBox}>
            <Ionicons name="construct-outline" size={32} color={colors.muted} />
            <Text style={styles.empty}>Selecione um cliente para ver/gerenciar os equipamentos dele.</Text>
          </View>
        )}
      </View>

      {cliente && canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="novo-equipamento">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <AppModal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editing ? `Equipamento #${editing.codigo}` : "Novo equipamento"}</Text>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Número de Série *</Text>
                  <TextInput value={numeroSerie} onChangeText={setNumeroSerie} style={styles.input} placeholder="Nº de série" placeholderTextColor={colors.muted} autoCapitalize="characters" testID="equip-numero-serie" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Número de Série Interno</Text>
                  <TextInput value={numeroSerieInt} onChangeText={setNumeroSerieInt} style={styles.input} placeholder="Se vazio, usa o Nº de série" placeholderTextColor={colors.muted} autoCapitalize="characters" testID="equip-numero-serie-int" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Marca *</Text>
                  <SelectField value={marca} onChange={(v) => { setMarca(v == null ? null : String(v)); setModelo(null); }} options={marcasOpts} placeholder="Selecione…" allowClear compactWeb testID="equip-marca" modalTitle="Marca" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Modelo *</Text>
                  <SelectField value={modelo} onChange={(v) => setModelo(v == null ? null : String(v))} options={modelosOpts} placeholder="Selecione…" allowClear compactWeb disabled={!marca} testID="equip-modelo" modalTitle="Modelo" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Usuário</Text>
                  <TextInput value={portador} onChangeText={setPortador} style={styles.input} placeholder="Portador/usuário do equipamento" placeholderTextColor={colors.muted} testID="equip-portador" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Local</Text>
                  <TextInput value={local} onChangeText={setLocal} style={styles.input} placeholder="Local" placeholderTextColor={colors.muted} testID="equip-local" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data de Revisão</Text>
                  <WebDateField value={revisao} onChange={(v) => setRevisao(v || null)} testID="equip-data-revisao" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor</Text>
                  <TextInput value={valor} onChangeText={setValor} style={styles.input} placeholder="0,00" placeholderTextColor={colors.muted} keyboardType="decimal-pad" testID="equip-valor" />
                </View>
                <View style={styles.colFlex}>
                  <View style={styles.situacaoRow}>
                    <Text style={styles.label}>Ativo</Text>
                    <Switch value={ativo} onValueChange={setAtivo} testID="equip-ativo" />
                  </View>
                </View>
              </View>

              <View style={styles.obsHeaderRow}>
                <Text style={styles.label}>Descrição</Text>
                <Pressable onPress={sugerirDescricao} style={styles.novaAnotacaoBtn} testID="sugerir-descricao">
                  <Ionicons name="sparkles-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.novaAnotacaoText}>Sugerir (Marca/Modelo)</Text>
                </Pressable>
              </View>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} placeholder="Descrição do equipamento" placeholderTextColor={colors.muted} maxLength={50} testID="equip-descricao" />

              <Text style={styles.label}>Tipo do Equipamento{!canAlterarTipo ? " (somente leitura)" : ""}</Text>
              <View style={styles.tipoRow}>
                <Pressable
                  disabled={!canAlterarTipo}
                  onPress={() => setTipoEquipamento("A")}
                  style={[styles.tipoBtn, tipoEquipamento === "A" && styles.tipoBtnSel, !canAlterarTipo && { opacity: 0.6 }]}
                  testID="equip-tipo-avulso"
                >
                  <Text style={[styles.tipoBtnText, tipoEquipamento === "A" && styles.tipoBtnTextSel]}>Avulso</Text>
                </Pressable>
                <Pressable
                  disabled={!canAlterarTipo}
                  onPress={() => setTipoEquipamento("C")}
                  style={[styles.tipoBtn, tipoEquipamento === "C" && styles.tipoBtnSel, !canAlterarTipo && { opacity: 0.6 }]}
                  testID="equip-tipo-contrato"
                >
                  <Text style={[styles.tipoBtnText, tipoEquipamento === "C" && styles.tipoBtnTextSel]}>Contrato</Text>
                </Pressable>
              </View>

              <Text style={styles.label}>Detalhes do Equipamento</Text>
              <TextInput value={detalhe} onChangeText={setDetalhe} style={[styles.input, styles.inputMultiline]} multiline placeholder="Detalhes/observações" placeholderTextColor={colors.muted} testID="equip-detalhe" />

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="equip-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={altSerieOpen} transparent animationType="slide" onRequestClose={() => setAltSerieOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setAltSerieOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Alterar Número de Série</Text>
            <Text style={styles.label}>Novo Número de Série *</Text>
            <TextInput value={altSerieNovo} onChangeText={setAltSerieNovo} style={styles.input} autoCapitalize="characters" testID="alt-serie-novo" />
            <Pressable onPress={confirmarAlterarSerie} disabled={altSerieSaving} style={[styles.primaryBtn, altSerieSaving && { opacity: 0.6 }]} testID="alt-serie-confirmar">
              {altSerieSaving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Confirmar</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>

      <ClientSearchModal
        visible={clienteSearchOpen}
        onClose={() => setClienteSearchOpen(false)}
        term={clienteSearchTerm}
        setTerm={setClienteSearchTerm}
        loading={clienteSearchLoading}
        results={clienteSearchResults}
        onPick={(c) => { setCliente(c); setClienteSearchOpen(false); }}
        onCreate={() => {
          setClienteSearchOpen(false);
          router.push({ pathname: "/cliente-form", params: { initial_nome: clienteSearchTerm } });
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
  clienteBox: { padding: spacing.lg, paddingBottom: spacing.sm },
  clienteRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  clienteNome: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  trocarText: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  selecionarClienteBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12 },
  selecionarClienteText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  emptyClienteBox: { alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingVertical: 60 },
  filterBox: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  filterRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  colNarrow: { width: 160 },
  colFlex: { flex: 1, minWidth: 160 },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  exportBtn: { width: 42, height: 42, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  rowSerie: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  badgeAvulso: { backgroundColor: "#DCFCE7" },
  badgeContrato: { backgroundColor: "#DBEAFE" },
  badgeInativo: { backgroundColor: "#FEE2E2", paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  badgeText: { fontSize: 11, fontWeight: "700", color: colors.onSurface },
  rowDesc: { fontSize: 13, color: colors.onSurface, marginTop: 4 },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  rowActions: { flexDirection: "row", gap: spacing.md },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8 },
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
  inputMultiline: { minHeight: 80, textAlignVertical: "top" },
  situacaoRow: { flexDirection: "row", alignItems: "center", justifyContent: "flex-start", gap: spacing.sm, marginTop: spacing.sm },
  obsHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  novaAnotacaoBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  novaAnotacaoText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  tipoRow: { flexDirection: "row", gap: spacing.sm },
  tipoBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" },
  tipoBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  tipoBtnTextSel: { color: colors.onBrandPrimary },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
