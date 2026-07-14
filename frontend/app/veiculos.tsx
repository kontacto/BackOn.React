import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type VeiculoItem = {
  codigo: number; placa: string; descricao: string; situacao: string;
  marca_desc: string; modelo_desc: string; motorista_nome: string;
};
type RotaVinculo = { rota: number; descricao: string };
type VeiculoDetalhe = {
  codigo: number; placa: string; descricao: string; motorista: number | null; auxiliar: number | null;
  hodometro: number | null; km: number | null; data_compra: string | null; valor_compra: number | null;
  peso_max: number | null; volume_max: number | null; peso_min: number | null; volume_min: number | null;
  marca: string | null; modelo: string | null; cor: string | null; motor: string; renavam: string; chassi: string;
  combustivel: string | null; ano_fab: number | null; ano_mod: number | null; tipo: string | null; situacao: string;
  doc_proprietario: string; rntrc_proprietario: string; nome_proprietario: string; ie_proprietario: string;
  uf_proprietario: string; tpRod: string; tpCar: string; UF: string; rotas: RotaVinculo[];
};

const COMBUSTIVEL_OPTS: SelectOption[] = [
  { value: "0", label: "Álcool" },
  { value: "1", label: "Gasolina" },
  { value: "2", label: "Diesel" },
];
const TIPO_OPTS: SelectOption[] = [
  { value: "0", label: "Caminhão" },
  { value: "1", label: "Carro" },
  { value: "2", label: "Moto" },
];
const TP_ROD_OPTS: SelectOption[] = [
  { value: "01", label: "01 - Truck" },
  { value: "02", label: "02 - Toco" },
  { value: "03", label: "03 - Cavalo Mecânico" },
  { value: "04", label: "04 - VAN" },
  { value: "05", label: "05 - Utilitário" },
  { value: "06", label: "06 - Outros" },
];
const TP_CAR_OPTS: SelectOption[] = [
  { value: "00", label: "00 - Não aplicável" },
  { value: "01", label: "01 - Aberta" },
  { value: "02", label: "02 - Fechada/Baú" },
  { value: "03", label: "03 - Granelera" },
  { value: "04", label: "04 - Porta Container" },
  { value: "05", label: "05 - Sider" },
];

const num = (s: string): number | null => (s.trim() ? parseFloat(s.replace(",", ".")) : null);
const int_ = (s: string): number | null => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) : null);

// Cadastro > Veículos (tabela `veiculos_transp` + N:N `veiculos_rota`). Legado:
// FrmManVei ("Cadastro de Veículos..."). Tela liberada pela flag de módulo
// `Cilindro` (Configurações > Módulos e Recursos) OU para o usuário master —
// gate aplicado no hub `app/(tabs)/cadastros.tsx`, não nesta tela (que só
// confere permissão de grupo normalmente via `can()`).
//
// Desvio deliberado do legado: o Gravar original decide Inserir/Alterar
// consultando pela PLACA digitada — renomear a Placa de um registro existente
// silenciosamente cria uma linha NOVA no legado. Aqui o app sempre grava pelo
// `codigo` (IDENTITY) do registro sendo editado; Placa duplicada em outro
// veículo é bloqueada com mensagem clara em vez do bug silencioso.
//
// Bug de validação corrigido: o legado, ao validar "Tipo", checa
// `Motorista.ListIndex` de novo (copy-paste) — na prática nunca exige Tipo
// preenchido. Aqui Tipo é obrigatório de verdade.
export default function VeiculosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Veículos está disponível apenas no web."
        testID="veiculos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<VeiculoItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [motoristaOptions, setMotoristaOptions] = useState<SelectOption[]>([]);
  const [auxiliarOptions, setAuxiliarOptions] = useState<SelectOption[]>([]);
  const [marcaOptions, setMarcaOptions] = useState<SelectOption[]>([]);
  const [modeloOptions, setModeloOptions] = useState<SelectOption[]>([]);
  const [corOptions, setCorOptions] = useState<SelectOption[]>([]);
  const [rotaOptions, setRotaOptions] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCodigo, setEditingCodigo] = useState<number | null>(null);
  const [placa, setPlaca] = useState("");
  const [descricao, setDescricao] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [tipo, setTipo] = useState<string | null>(null);
  const [combustivel, setCombustivel] = useState<string | null>(null);
  const [tpRod, setTpRod] = useState<string | null>(null);
  const [tpCar, setTpCar] = useState<string | null>(null);
  const [motorista, setMotorista] = useState<number | null>(null);
  const [auxiliar, setAuxiliar] = useState<number | null>(null);
  const [marca, setMarca] = useState<string | null>(null);
  const [modelo, setModelo] = useState<string | null>(null);
  const [cor, setCor] = useState<string | null>(null);
  const [motor, setMotor] = useState("");
  const [renavam, setRenavam] = useState("");
  const [chassi, setChassi] = useState("");
  const [anoFab, setAnoFab] = useState("");
  const [anoMod, setAnoMod] = useState("");
  const [ufLicenca, setUfLicenca] = useState("");
  const [hodometro, setHodometro] = useState("");
  const [km, setKm] = useState("");
  const [dataCompra, setDataCompra] = useState<string | null>(null);
  const [valorCompra, setValorCompra] = useState("");
  const [pesoMax, setPesoMax] = useState("");
  const [pesoMin, setPesoMin] = useState("");
  const [volumeMax, setVolumeMax] = useState("");
  const [volumeMin, setVolumeMin] = useState("");
  const [docProprietario, setDocProprietario] = useState("");
  const [rntrcProprietario, setRntrcProprietario] = useState("");
  const [nomeProprietario, setNomeProprietario] = useState("");
  const [ieProprietario, setIeProprietario] = useState("");
  const [ufProprietario, setUfProprietario] = useState("");
  const [rotas, setRotas] = useState<RotaVinculo[]>([]);
  const [novaRota, setNovaRota] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/veiculos?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rMot, rAux, rMarca, rCor, rRota] = await Promise.all([
        fetch(`${base}/api/veiculos/motoristas?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/veiculos/auxiliares?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/marcas?${qs}&marca_produto=false`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/cores?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/rotas?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rMot?.success) setMotoristaOptions((rMot.items || []).map((i: any) => ({ value: i.codigo, label: i.nome })));
      if (rAux?.success) setAuxiliarOptions((rAux.items || []).map((i: any) => ({ value: i.codigo, label: i.nome })));
      if (rMarca?.success) setMarcaOptions((rMarca.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rCor?.success) setCorOptions((rCor.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rRota?.success) setRotaOptions((rRota.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  const loadModelos = useCallback(async (c: Conn, codMarca: string | null) => {
    if (!codMarca) { setModeloOptions([]); return; }
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&cod_marca=${encodeURIComponent(codMarca)}`;
      const r = await fetch(`${base}/api/tabelas/modelos?${qs}`).then((x) => x.json());
      setModeloOptions(r?.success ? (r.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })) : []);
    } catch { setModeloOptions([]); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc, "");
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const resetForm = () => {
    setPlaca(""); setDescricao(""); setSituacao("A"); setTipo(null); setCombustivel(null);
    setTpRod(null); setTpCar(null); setMotorista(null); setAuxiliar(null); setMarca(null); setModelo(null);
    setCor(null); setMotor(""); setRenavam(""); setChassi(""); setAnoFab(""); setAnoMod(""); setUfLicenca("");
    setHodometro(""); setKm(""); setDataCompra(null); setValorCompra(""); setPesoMax(""); setPesoMin("");
    setVolumeMax(""); setVolumeMin(""); setDocProprietario(""); setRntrcProprietario(""); setNomeProprietario("");
    setIeProprietario(""); setUfProprietario(""); setRotas([]); setNovaRota(null);
    setModeloOptions([]);
  };

  const openNew = () => {
    setEditingCodigo(null);
    resetForm();
    setFormOpen(true);
  };

  const openEdit = async (item: VeiculoItem) => {
    if (!conn) return;
    setEditingCodigo(item.codigo);
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/veiculos/${item.codigo}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d: VeiculoDetalhe = j.veiculo;
      setPlaca(d.placa); setDescricao(d.descricao); setSituacao(d.situacao || "A");
      setTipo(d.tipo); setCombustivel(d.combustivel); setTpRod(d.tpRod || null); setTpCar(d.tpCar || null);
      setMotorista(d.motorista); setAuxiliar(d.auxiliar); setMarca(d.marca); setCor(d.cor);
      setMotor(d.motor); setRenavam(d.renavam); setChassi(d.chassi);
      setAnoFab(d.ano_fab != null ? String(d.ano_fab) : ""); setAnoMod(d.ano_mod != null ? String(d.ano_mod) : "");
      setUfLicenca(d.UF || "");
      setHodometro(d.hodometro != null ? String(d.hodometro) : ""); setKm(d.km != null ? String(d.km) : "");
      setDataCompra(d.data_compra); setValorCompra(d.valor_compra != null ? String(d.valor_compra) : "");
      setPesoMax(d.peso_max != null ? String(d.peso_max) : ""); setPesoMin(d.peso_min != null ? String(d.peso_min) : "");
      setVolumeMax(d.volume_max != null ? String(d.volume_max) : ""); setVolumeMin(d.volume_min != null ? String(d.volume_min) : "");
      setDocProprietario(d.doc_proprietario); setRntrcProprietario(d.rntrc_proprietario);
      setNomeProprietario(d.nome_proprietario); setIeProprietario(d.ie_proprietario); setUfProprietario(d.uf_proprietario);
      setRotas(d.rotas || []);
      await loadModelos(conn, d.marca);
      setModelo(d.modelo);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const onChangeMarca = (v: string | number | null) => {
    const codMarca = v ? String(v) : null;
    setMarca(codMarca);
    setModelo(null);
    if (conn) loadModelos(conn, codMarca);
  };

  const save = async () => {
    if (!conn) return;
    if (!placa.trim()) { fb.showWarning("Defina a Placa do Veículo!"); return; }
    if (!motorista) { fb.showWarning("Defina o Motorista do Veículo!"); return; }
    if (!marca) { fb.showWarning("Defina a Marca do Veículo!"); return; }
    if (!modelo) { fb.showWarning("Defina o Modelo do Veículo!"); return; }
    if (!cor) { fb.showWarning("Defina a Cor do Veículo!"); return; }
    if (!combustivel) { fb.showWarning("Defina o Combustível do Veículo!"); return; }
    if (!tipo) { fb.showWarning("Defina o Tipo do Veículo!"); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/veiculos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: editingCodigo, placa: placa.trim().toUpperCase(), descricao: descricao.trim(),
          motorista, auxiliar, hodometro: num(hodometro), km: num(km),
          data_compra: dataCompra, valor_compra: num(valorCompra),
          peso_max: int_(pesoMax), volume_max: int_(volumeMax), peso_min: int_(pesoMin), volume_min: int_(volumeMin),
          marca, modelo, cor, motor: motor.trim(), renavam: renavam.trim(), chassi: chassi.trim(),
          combustivel, ano_fab: int_(anoFab), ano_mod: int_(anoMod), tipo, situacao: situacao.trim().toUpperCase(),
          doc_proprietario: docProprietario.trim(), rntrc_proprietario: rntrcProprietario.trim(),
          nome_proprietario: nomeProprietario.trim(), ie_proprietario: ieProprietario.trim(),
          uf_proprietario: ufProprietario.trim().toUpperCase(),
          tpRod: tpRod || "", tpCar: tpCar || "", UF: ufLicenca.trim().toUpperCase(),
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Veículo gravado.");
        if (!editingCodigo && j.codigo) setEditingCodigo(j.codigo);
        load(conn, search);
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = (item: VeiculoItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão do veículo "${item.placa}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/veiculos/${item.codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn, search); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const vincularRota = async () => {
    if (!conn || !editingCodigo || !novaRota) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/veiculos/${editingCodigo}/rotas`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, rota: novaRota }),
      });
      const j = await r.json();
      if (j?.success) {
        const opt = rotaOptions.find((o) => String(o.value) === String(novaRota));
        setRotas((prev) => [...prev, { rota: novaRota, descricao: opt?.label || String(novaRota) }]);
        setNovaRota(null);
      } else fb.showError(j?.message || "Falha ao vincular rota.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const desvincularRota = async (rota: number) => {
    if (!conn || !editingCodigo) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/veiculos/${editingCodigo}/rotas/${rota}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) setRotas((prev) => prev.filter((x) => x.rota !== rota));
      else fb.showError(j?.message || "Falha ao remover rota.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("VEICULOS.GRAVAR") || isMaster;
  const canDel = can("VEICULOS.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="veiculos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Veículos</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por placa ou descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="veiculos-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum veículo cadastrado.</Text> : null}
          {items.map((v) => (
            <View key={v.codigo} style={styles.row} testID={`veiculos-${v.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(v)}>
                <Text style={styles.rowTitle}>{v.placa} · {v.descricao || "—"}</Text>
                <Text style={styles.rowSub}>
                  {[v.marca_desc, v.modelo_desc].filter(Boolean).join(" ") || "Sem marca/modelo"}
                  {v.motorista_nome ? ` · ${v.motorista_nome}` : ""}
                  {v.situacao && v.situacao !== "A" ? ` · ${v.situacao}` : ""}
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(v)} hitSlop={8} testID={`veiculos-del-${v.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="veiculos-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editingCodigo ? `Veículo ${placa}` : "Novo veículo"}</Text>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.label}>Placa *</Text>
              <TextInput value={placa} onChangeText={(v) => setPlaca(v.toUpperCase())} style={styles.input} maxLength={7} autoCapitalize="characters" testID="veiculos-placa" />

              <Text style={styles.label}>Descrição</Text>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={30} testID="veiculos-descricao" />

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Situação</Text>
                  <TextInput value={situacao} onChangeText={(v) => setSituacao(v.toUpperCase())} style={styles.input} maxLength={2} testID="veiculos-situacao" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>UF licença</Text>
                  <TextInput value={ufLicenca} onChangeText={(v) => setUfLicenca(v.toUpperCase())} style={styles.input} maxLength={2} autoCapitalize="characters" testID="veiculos-uf" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Classificação</Text>
              <Text style={styles.label}>Tipo *</Text>
              <SelectField value={tipo} onChange={(v) => setTipo(v as string)} options={TIPO_OPTS} testID="veiculos-tipo" modalTitle="Tipo" compactWeb />
              <Text style={styles.label}>Combustível *</Text>
              <SelectField value={combustivel} onChange={(v) => setCombustivel(v as string)} options={COMBUSTIVEL_OPTS} testID="veiculos-combustivel" modalTitle="Combustível" compactWeb />
              <Text style={styles.label}>Tipo de Rodado</Text>
              <SelectField value={tpRod} onChange={(v) => setTpRod(v as string)} options={TP_ROD_OPTS} allowClear testID="veiculos-tprod" modalTitle="Tipo de Rodado" compactWeb />
              <Text style={styles.label}>Tipo de Carroceria</Text>
              <SelectField value={tpCar} onChange={(v) => setTpCar(v as string)} options={TP_CAR_OPTS} allowClear testID="veiculos-tpcar" modalTitle="Tipo de Carroceria" compactWeb />

              <Text style={styles.sectionTitle}>Motorista</Text>
              <Text style={styles.label}>Motorista *</Text>
              <SelectField value={motorista} onChange={(v) => setMotorista(v as number)} options={motoristaOptions} testID="veiculos-motorista" modalTitle="Motorista" compactWeb />
              <Text style={styles.label}>Auxiliar</Text>
              <SelectField value={auxiliar} onChange={(v) => setAuxiliar(v as number)} options={auxiliarOptions} allowClear testID="veiculos-auxiliar" modalTitle="Auxiliar" compactWeb />

              <Text style={styles.sectionTitle}>Veículo</Text>
              <Text style={styles.label}>Marca *</Text>
              <SelectField value={marca} onChange={onChangeMarca} options={marcaOptions} testID="veiculos-marca" modalTitle="Marca" compactWeb />
              <Text style={styles.label}>Modelo *</Text>
              <SelectField value={modelo} onChange={(v) => setModelo(v as string)} options={modeloOptions} testID="veiculos-modelo" modalTitle="Modelo" compactWeb />
              <Text style={styles.label}>Cor *</Text>
              <SelectField value={cor} onChange={(v) => setCor(v as string)} options={corOptions} testID="veiculos-cor" modalTitle="Cor" compactWeb />

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Ano Fabricação</Text>
                  <TextInput value={anoFab} onChangeText={(v) => setAnoFab(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" maxLength={4} testID="veiculos-ano-fab" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Ano Modelo</Text>
                  <TextInput value={anoMod} onChangeText={(v) => setAnoMod(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" maxLength={4} testID="veiculos-ano-mod" />
                </View>
              </View>

              <Text style={styles.label}>Motor</Text>
              <TextInput value={motor} onChangeText={setMotor} style={styles.input} maxLength={13} testID="veiculos-motor" />
              <Text style={styles.label}>Renavam</Text>
              <TextInput value={renavam} onChangeText={setRenavam} style={styles.input} maxLength={10} testID="veiculos-renavam" />
              <Text style={styles.label}>Chassi</Text>
              <TextInput value={chassi} onChangeText={setChassi} style={styles.input} maxLength={18} autoCapitalize="characters" testID="veiculos-chassi" />

              <Text style={styles.sectionTitle}>Uso</Text>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Hodômetro</Text>
                  <TextInput value={hodometro} onChangeText={setHodometro} style={styles.input} keyboardType="decimal-pad" testID="veiculos-hodometro" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Km</Text>
                  <TextInput value={km} onChangeText={setKm} style={styles.input} keyboardType="decimal-pad" testID="veiculos-km" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <DateField label="Data Compra" value={dataCompra} onChange={setDataCompra} testID="veiculos-data-compra" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Valor Compra</Text>
                  <TextInput value={valorCompra} onChangeText={setValorCompra} style={styles.input} keyboardType="decimal-pad" testID="veiculos-valor-compra" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Peso Máximo</Text>
                  <TextInput value={pesoMax} onChangeText={(v) => setPesoMax(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="veiculos-peso-max" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Peso Mínimo</Text>
                  <TextInput value={pesoMin} onChangeText={(v) => setPesoMin(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="veiculos-peso-min" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Volume Máximo</Text>
                  <TextInput value={volumeMax} onChangeText={(v) => setVolumeMax(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="veiculos-volume-max" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Volume Mínimo</Text>
                  <TextInput value={volumeMin} onChangeText={(v) => setVolumeMin(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="veiculos-volume-min" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Dados do proprietário</Text>
              <Text style={styles.sectionHint}>Quando o veículo não pertencer à empresa emitente do MDF-e.</Text>
              <Text style={styles.label}>CNPJ/CPF</Text>
              <TextInput value={docProprietario} onChangeText={setDocProprietario} style={styles.input} maxLength={14} keyboardType="number-pad" testID="veiculos-doc-proprietario" />
              <Text style={styles.label}>Registro Nacional (RNTRC)</Text>
              <TextInput value={rntrcProprietario} onChangeText={setRntrcProprietario} style={styles.input} maxLength={8} testID="veiculos-rntrc" />
              <Text style={styles.label}>Nome</Text>
              <TextInput value={nomeProprietario} onChangeText={setNomeProprietario} style={styles.input} maxLength={60} testID="veiculos-nome-proprietario" />
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Insc. Estadual</Text>
                  <TextInput value={ieProprietario} onChangeText={setIeProprietario} style={styles.input} maxLength={14} testID="veiculos-ie-proprietario" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>UF</Text>
                  <TextInput value={ufProprietario} onChangeText={(v) => setUfProprietario(v.toUpperCase())} style={styles.input} maxLength={2} autoCapitalize="characters" testID="veiculos-uf-proprietario" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Rotas</Text>
              {editingCodigo ? (
                <>
                  <View style={styles.rowFields}>
                    <View style={{ flex: 1 }}>
                      <SelectField value={novaRota} onChange={(v) => setNovaRota(v as number)} options={rotaOptions} testID="veiculos-nova-rota" modalTitle="Rota" compactWeb />
                    </View>
                    <Pressable onPress={vincularRota} disabled={!novaRota} style={[styles.addBtn, !novaRota && { opacity: 0.5 }]} testID="veiculos-vincular-rota">
                      <Ionicons name="add" size={16} color={colors.brandPrimary} />
                      <Text style={styles.addBtnText}>Vincular</Text>
                    </Pressable>
                  </View>
                  {rotas.length === 0 ? <Text style={styles.empty}>Nenhuma rota vinculada.</Text> : null}
                  {rotas.map((r) => (
                    <View key={r.rota} style={styles.rotaRow} testID={`veiculos-rota-${r.rota}`}>
                      <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{r.descricao}</Text>
                      <Pressable onPress={() => desvincularRota(r.rota)} hitSlop={8} testID={`veiculos-rota-del-${r.rota}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    </View>
                  ))}
                </>
              ) : (
                <Text style={styles.sectionHint}>Salve o veículo primeiro para vincular rotas.</Text>
              )}

              {canSave ? (
                <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="veiculos-salvar">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
    paddingVertical: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 640 : undefined,
    maxHeight: "92%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.lg : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs },
  sectionHint: { fontSize: 11, color: colors.muted, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  colHalf: { flex: 1 },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 11, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border },
  addBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  rotaRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, padding: spacing.sm,
  },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
