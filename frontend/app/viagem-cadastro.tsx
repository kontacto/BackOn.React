// Manutenção de Viagens (módulo Cilindros). Legado: FrmManViagens.frm
// ("Manutenção de Viagens..."). Ver PENDENCIAS.md > "Cilindros" > "Fase 3"
// pro rastreio completo. Tela compacta sem abas (o legado também não tem
// controle de abas aqui — mesmo precedente de fornecedores.tsx/
// cilindro-cadastro.tsx).
//
// Escopo desta rodada (backend: services/viagem_service.py): cabeçalho da
// viagem, item manual (Adicionar/Excluir/Alterar Cilindro), Fechar Saída,
// Fechar Entrada (motor de críticas + reconciliação de estoque/contratos),
// Reabrir, Cancelar, Renumerar. NÃO implementado: "Adicionar Pedidos"
// (inclusão em massa a partir de Pedido_Venda), "Adicionar Itens do Pátio",
// "Itens Avulsos de Entrada", impressão formatada — ver PENDENCIAS.md.
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import WebDateField from "@/src/components/WebDateField";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;
const isCompactWeb = Platform.OS === "web";

const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);

type ViagemListItem = {
  codigo: number; tipo_viagem: number; situacao: string; saida: string | null; hora_saida: string | null;
  retorno: string | null; hora_retorno: string | null; saida_fechada: boolean; entrada_fechada: boolean;
  placa: string | null; veiculo_descricao: string | null; motorista_nome: string | null; ajudante_nome: string | null;
};

type ViagemItem = {
  codigo: number; ordem: number; cliente: number; cliente_nome: string | null;
  cilindro: number; cil_codigo: string; cil_capacidade: number; cil_pressao: number; cil_padrao: string;
  num_serie: number | null; nds_saida: string | null;
  status_saida: string; os_saida: string; carga_saida: number; obs_saida: string;
  doc_saida: number; tipo_doc_saida: number;
  cilindro_retorno: number | null; cilr_codigo: string | null; cilr_capacidade: number | null; cilr_pressao: number | null;
  num_serie_retorno: number | null; nds_retorno: string | null;
  status_retorno: string | null; os_retorno: string | null; carga_retorno: number | null; obs_retorno: string | null;
  nf_retorno: number | null;
};

type ViagemHeader = {
  codigo: number; veiculo: number; placa: string | null; veiculo_descricao: string | null;
  motorista: number | null; motorista_nome: string | null; ajudante: number | null; ajudante_nome: string | null;
  tipo_viagem: number; descricao: string; obs: string;
  saida: string | null; hora_saida: string | null; km_saida: number;
  retorno: string | null; hora_retorno: string | null; km_retorno: number;
  saida_fechada: boolean; entrada_fechada: boolean; situacao: string;
  itens: ViagemItem[];
};

type PickerRow = { codigo: number; nome: string; sub?: string };
type CilindroRow = { cod: number; codigo: string; capacidade: number; pressao: number; padrao: string; descricao: string };

export default function ViagemCadastroScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Viagens está disponível apenas no web."
        testID="viagem-cadastro-web-only"
      />
    );
  }

  const canOpen = can("VIAGEM.ABRIR") || isMaster;
  const canGravar = can("VIAGEM.GRAVAR") || isMaster;
  const canAddItem = can("VIAGEM.ADD_ITEM") || isMaster;
  const canDelItem = can("VIAGEM.DEL_ITEM") || isMaster;
  const canAlterarCilindro = can("VIAGEM.ALT_CILINDRO") || isMaster;
  const canFecharSaida = can("VIAGEM.FECHAR_SAIDA") || isMaster;
  const canFecharEntrada = can("VIAGEM.FECHAR_ENTRADA") || isMaster;
  const canReabrir = can("VIAGEM.REABRIR") || isMaster;
  const canCancelar = can("VIAGEM.CANCELAR") || isMaster;

  const [conn, setConn] = useState<Conn | null>(null);

  const [motoristaOptions, setMotoristaOptions] = useState<SelectOption[]>([]);
  const [auxiliarOptions, setAuxiliarOptions] = useState<SelectOption[]>([]);
  const [situacaoItemOptions, setSituacaoItemOptions] = useState<SelectOption[]>([]);

  // ---- Lista / Consulta ----
  const [items, setItems] = useState<ViagemListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  // ---- Formulário (cabeçalho da viagem aberta) ----
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [viagem, setViagem] = useState<ViagemHeader | null>(null);

  const [veiculo, setVeiculo] = useState<PickerRow | null>(null);
  const [motorista, setMotorista] = useState<string | null>(null);
  const [ajudante, setAjudante] = useState<string | null>(null);
  const [tipoViagem, setTipoViagem] = useState<0 | 1>(0);
  const [descricao, setDescricao] = useState("");
  const [obs, setObs] = useState("");
  const [dataSaida, setDataSaida] = useState<string | null>(null);
  const [horaSaida, setHoraSaida] = useState<string | null>(null);
  const [kmSaida, setKmSaida] = useState("");
  const [dataRetorno, setDataRetorno] = useState<string | null>(null);
  const [horaRetorno, setHoraRetorno] = useState<string | null>(null);
  const [kmRetorno, setKmRetorno] = useState("");

  // ---- Picker de Veículo ----
  const [veiculoPickerOpen, setVeiculoPickerOpen] = useState(false);
  const [veiculoBusca, setVeiculoBusca] = useState("");
  const [veiculoResultados, setVeiculoResultados] = useState<PickerRow[]>([]);
  const [veiculoBuscando, setVeiculoBuscando] = useState(false);

  // ---- Pickers compartilhados (Cliente / Fornecedor / Cilindro) ----
  const [clientePickerOpen, setClientePickerOpen] = useState(false);
  const [clienteBusca, setClienteBusca] = useState("");
  const [clienteResultados, setClienteResultados] = useState<PickerRow[]>([]);
  const [clienteBuscando, setClienteBuscando] = useState(false);

  const [cilindroPickerOpen, setCilindroPickerOpen] = useState(false);
  const [cilindroPickerTarget, setCilindroPickerTarget] = useState<"item" | "retorno" | "alterar">("item");
  const [cilindroBusca, setCilindroBusca] = useState("");
  const [cilindroResultados, setCilindroResultados] = useState<CilindroRow[]>([]);
  const [cilindroBuscando, setCilindroBuscando] = useState(false);

  // ---- Modal Adicionar Item (lado Saída) ----
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [itemCliente, setItemCliente] = useState<PickerRow | null>(null);
  const [itemCilindro, setItemCilindro] = useState<CilindroRow | null>(null);
  const [itemNumeroSerie, setItemNumeroSerie] = useState("");
  const [itemStatus, setItemStatus] = useState<string | null>(null);
  const [itemDocSaida, setItemDocSaida] = useState("");
  const [itemOsSaida, setItemOsSaida] = useState("");
  const [itemCarga, setItemCarga] = useState<"CHEIO" | "VAZIO">("CHEIO");
  const [itemObs, setItemObs] = useState("");
  const [itemSaving, setItemSaving] = useState(false);

  // ---- Modal Registrar Retorno ----
  const [retornoModalOpen, setRetornoModalOpen] = useState(false);
  const [retornoItemCodigo, setRetornoItemCodigo] = useState<number | null>(null);
  const [retornoCilindro, setRetornoCilindro] = useState<CilindroRow | null>(null);
  const [retornoNumeroSerie, setRetornoNumeroSerie] = useState("");
  const [retornoStatus, setRetornoStatus] = useState<string | null>(null);
  const [retornoNf, setRetornoNf] = useState("");
  const [retornoOs, setRetornoOs] = useState("");
  const [retornoCarga, setRetornoCarga] = useState<"CHEIO" | "VAZIO">("CHEIO");
  const [retornoObs, setRetornoObs] = useState("");
  const [retornoSaving, setRetornoSaving] = useState(false);

  // ---- Alterar Cilindro ----
  const [alterarItemCodigo, setAlterarItemCodigo] = useState<number | null>(null);

  const base = () => (conn ? conn.api.replace(/\/+$/, "") : "");
  const qsConn = () => (conn ? `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` : "");

  const loadLookups = useCallback(async (c: Conn) => {
    const b = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rMot, rAux, rSit] = await Promise.all([
        fetch(`${b}/api/veiculos/motoristas?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${b}/api/veiculos/auxiliares?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${b}/api/cilindro-situacao?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rMot?.success) setMotoristaOptions(rMot.items.map((i: any) => ({ value: i.codigo, label: i.nome })));
      if (rAux?.success) setAuxiliarOptions(rAux.items.map((i: any) => ({ value: i.codigo, label: i.nome })));
      if (rSit?.success) setSituacaoItemOptions(rSit.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  const loadList = useCallback(async (c: Conn, term?: string) => {
    setLoading(true);
    try {
      const b = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}${term ? `&codigo=${encodeURIComponent(term)}` : ""}`;
      const r = await fetch(`${b}/api/viagens?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      loadList(c);
      loadLookups(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const resetHeaderForm = () => {
    setViagem(null);
    setVeiculo(null); setMotorista(null); setAjudante(null); setTipoViagem(0);
    setDescricao(""); setObs("");
    setDataSaida(null); setHoraSaida(null); setKmSaida("");
    setDataRetorno(null); setHoraRetorno(null); setKmRetorno("");
  };

  const openNew = () => {
    resetHeaderForm();
    setFormOpen(true);
  };

  const carregarViagem = useCallback(async (codigo: number) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base()}/api/viagens/${codigo}?${qsConn()}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar viagem."); return; }
      const d: ViagemHeader = j.item;
      setViagem(d);
      setVeiculo(d.veiculo ? { codigo: d.veiculo, nome: `${d.placa || ""} — ${d.veiculo_descricao || ""}` } : null);
      setMotorista(d.motorista ? String(d.motorista) : null);
      setAjudante(d.ajudante ? String(d.ajudante) : null);
      setTipoViagem((d.tipo_viagem as 0 | 1) || 0);
      setDescricao(d.descricao || "");
      setObs(d.obs || "");
      setDataSaida(d.saida ? String(d.saida).slice(0, 10) : null);
      setHoraSaida(d.hora_saida ? String(d.hora_saida).slice(0, 5) : null);
      setKmSaida(d.km_saida ? String(d.km_saida) : "");
      setDataRetorno(d.retorno ? String(d.retorno).slice(0, 10) : null);
      setHoraRetorno(d.hora_retorno ? String(d.hora_retorno).slice(0, 5) : null);
      setKmRetorno(d.km_retorno ? String(d.km_retorno) : "");
      setFormOpen(true);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const salvarCabecalho = async () => {
    if (!conn) return;
    if (!veiculo) { fb.showWarning("Selecione o Veículo."); return; }
    setSaving(true);
    try {
      const r = await fetch(`${base()}/api/viagens`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: viagem?.codigo || null,
          dados: {
            veiculo: veiculo.codigo, motorista: motorista ? int_(motorista) : null, ajudante: ajudante ? int_(ajudante) : null,
            tipo_viagem: tipoViagem, descricao, obs,
            saida: dataSaida, hora_saida: horaSaida, km_saida: int_(kmSaida),
            retorno: dataRetorno, hora_retorno: horaRetorno, km_retorno: int_(kmRetorno),
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Dados da viagem gravados.");
        loadList(conn);
        carregarViagem(j.codigo);
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  // ---- Ações de ciclo de vida ----
  const executarAcao = async (path: string, mensagemSucesso: string, criticasCallback?: (criticas: string[]) => void) => {
    if (!conn || !viagem) return;
    setBusy(true);
    try {
      const r = await fetch(`${base()}/api/viagens/${viagem.codigo}/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || mensagemSucesso);
        carregarViagem(viagem.codigo);
        loadList(conn);
      } else if (j?.criticas?.length && criticasCallback) {
        criticasCallback(j.criticas);
      } else {
        fb.showError(j?.message || "Falha na operação.");
      }
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };

  const fecharSaida = () => executarAcao("fechar-saida", "Saída fechada com sucesso.");
  const fecharEntrada = () => executarAcao("fechar-entrada", "Entrada fechada com sucesso.", (criticas) => {
    Alert.alert("Críticas pendentes", criticas.join("\n\n"));
  });
  const reabrir = () => {
    Alert.alert("Reabrir", "Confirma reabrir a saída/entrada desta viagem?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Reabrir", onPress: () => executarAcao("reabrir", "Viagem reaberta.") },
    ]);
  };
  const cancelarViagem = () => {
    Alert.alert("Cancelar Viagem", "Confirma o cancelamento desta viagem? Os itens lançados serão removidos.", [
      { text: "Não", style: "cancel" },
      { text: "Sim, cancelar", style: "destructive", onPress: () => executarAcao("cancelar", "Viagem cancelada.") },
    ]);
  };
  const renumerar = () => executarAcao("renumerar", "Itens renumerados.");

  // ---- Picker de Veículo ----
  const buscarVeiculos = useCallback(async (termo: string) => {
    if (!conn) return;
    setVeiculoBuscando(true);
    try {
      const r = await fetch(`${base()}/api/veiculos?${qsConn()}&search=${encodeURIComponent(termo)}`);
      const j = await r.json();
      setVeiculoResultados(j?.success ? j.items.map((v: any) => ({ codigo: v.codigo, nome: v.placa, sub: v.descricao })) : []);
    } catch { setVeiculoResultados([]); } finally { setVeiculoBuscando(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const abrirVeiculoPicker = () => { setVeiculoBusca(""); setVeiculoResultados([]); setVeiculoPickerOpen(true); buscarVeiculos(""); };
  const selecionarVeiculo = (v: PickerRow) => { setVeiculo(v); setVeiculoPickerOpen(false); };

  // ---- Picker de Cliente/Fornecedor (destinatário do item) ----
  const buscarClientes = useCallback(async (termo: string) => {
    if (!conn) return;
    setClienteBuscando(true);
    try {
      const path = tipoViagem === 1 ? "/api/fornecedores" : "/api/clientes/find/search";
      const qsExtra = tipoViagem === 1 ? `search=${encodeURIComponent(termo)}` : `term=${encodeURIComponent(termo)}`;
      const r = await fetch(`${base()}${path}?${qsConn()}&${qsExtra}`);
      const j = await r.json();
      if (!j?.success) { setClienteResultados([]); return; }
      const rows: PickerRow[] = tipoViagem === 1
        ? j.items.map((f: any) => ({ codigo: f.codigo_int, nome: f.nome, sub: f.fantasia }))
        : j.items.map((c: any) => ({ codigo: c.codigo, nome: c.nome, sub: c.cgc_cpf }));
      setClienteResultados(rows);
    } catch { setClienteResultados([]); } finally { setClienteBuscando(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, tipoViagem]);

  const abrirClientePicker = () => { setClienteBusca(""); setClienteResultados([]); setClientePickerOpen(true); buscarClientes(""); };
  const selecionarCliente = (c: PickerRow) => { setItemCliente(c); setClientePickerOpen(false); };

  // ---- Picker de Cilindro (compartilhado) ----
  const buscarCilindros = useCallback(async (termo: string) => {
    if (!conn) return;
    setCilindroBuscando(true);
    try {
      const r = await fetch(`${base()}/api/cilindros?${qsConn()}&search=${encodeURIComponent(termo)}&size=30`);
      const j = await r.json();
      setCilindroResultados(j?.success ? j.items || [] : []);
    } catch { setCilindroResultados([]); } finally { setCilindroBuscando(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const abrirCilindroPicker = (target: "item" | "retorno" | "alterar") => {
    setCilindroPickerTarget(target);
    setCilindroBusca(""); setCilindroResultados([]); setCilindroPickerOpen(true);
    buscarCilindros("");
  };

  const selecionarCilindro = (c: CilindroRow) => {
    if (cilindroPickerTarget === "item") setItemCilindro(c);
    else if (cilindroPickerTarget === "retorno") setRetornoCilindro(c);
    else if (cilindroPickerTarget === "alterar" && alterarItemCodigo) {
      alterarCilindroConfirmado(alterarItemCodigo, c.cod);
    }
    setCilindroPickerOpen(false);
  };

  // ---- Adicionar Item ----
  const abrirNovoItem = () => {
    setItemCliente(null); setItemCilindro(null); setItemNumeroSerie(""); setItemStatus(null);
    setItemDocSaida(""); setItemOsSaida(""); setItemCarga("CHEIO"); setItemObs("");
    setItemModalOpen(true);
  };

  const salvarNovoItem = async () => {
    if (!conn || !viagem) return;
    if (!itemCliente) { fb.showWarning("Selecione o Destinatário."); return; }
    if (!itemCilindro) { fb.showWarning("Selecione o Cilindro."); return; }
    if (!itemStatus) { fb.showWarning("Selecione o Status de Saída."); return; }
    setItemSaving(true);
    try {
      const r = await fetch(`${base()}/api/viagens/${viagem.codigo}/itens`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          dados: {
            cliente: itemCliente.codigo, cilindro: itemCilindro.cod, status_saida: itemStatus,
            numero_serie: itemNumeroSerie.trim(), doc_saida: int_(itemDocSaida), tipo_doc_saida: 3,
            carga_saida: itemCarga, os_saida: itemOsSaida.trim(), obs_saida: itemObs,
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Item adicionado.");
        setItemModalOpen(false);
        carregarViagem(viagem.codigo);
      } else fb.showError(j?.message || "Falha ao adicionar item.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setItemSaving(false); }
  };

  const excluirItem = (item: ViagemItem) => {
    if (!conn || !viagem) return;
    Alert.alert("Excluir Item", `Confirma a exclusão do item de ordem ${item.ordem}?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const r = await fetch(`${base()}/api/viagens/itens/${item.codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); carregarViagem(viagem.codigo); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  // ---- Registrar Retorno ----
  const abrirRetorno = (item: ViagemItem) => {
    setRetornoItemCodigo(item.codigo);
    setRetornoCilindro(
      item.cilindro_retorno
        ? { cod: item.cilindro_retorno, codigo: item.cilr_codigo || "", capacidade: item.cil_capacidade, pressao: item.cil_pressao, padrao: item.cil_padrao, descricao: "" }
        : { cod: item.cilindro, codigo: item.cil_codigo, capacidade: item.cil_capacidade, pressao: item.cil_pressao, padrao: item.cil_padrao, descricao: "" },
    );
    setRetornoNumeroSerie(item.nds_retorno || "");
    setRetornoStatus(item.status_retorno || item.status_saida || null);
    setRetornoNf(item.nf_retorno ? String(item.nf_retorno) : "");
    setRetornoOs(item.os_retorno || item.os_saida || "");
    setRetornoCarga(item.carga_retorno === 1 ? "VAZIO" : "CHEIO");
    setRetornoObs(item.obs_retorno || "");
    setRetornoModalOpen(true);
  };

  const salvarRetorno = async () => {
    if (!conn || !retornoItemCodigo) return;
    if (!retornoCilindro) { fb.showWarning("Selecione o Cilindro de Retorno."); return; }
    if (!retornoStatus) { fb.showWarning("Selecione o Status de Retorno."); return; }
    setRetornoSaving(true);
    try {
      const r = await fetch(`${base()}/api/viagens/itens/${retornoItemCodigo}/retorno`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          dados: {
            cilindro_retorno: retornoCilindro.cod, status_retorno: retornoStatus,
            numero_serie_retorno: retornoNumeroSerie.trim(), nf_retorno: int_(retornoNf),
            os_retorno: retornoOs.trim(), carga_retorno: retornoCarga, obs_retorno: retornoObs,
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Retorno gravado.");
        setRetornoModalOpen(false);
        if (viagem) carregarViagem(viagem.codigo);
      } else fb.showError(j?.message || "Falha ao gravar retorno.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setRetornoSaving(false); }
  };

  // ---- Alterar Cilindro ----
  const alterarCilindroConfirmado = async (itemCodigo: number, novoCilindroCod: number) => {
    if (!conn) return;
    try {
      const r = await fetch(`${base()}/api/viagens/itens/${itemCodigo}/alterar-cilindro`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, cilindro: novoCilindroCod }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Cilindro alterado."); if (viagem) carregarViagem(viagem.codigo); }
      else fb.showError(j?.message || "Falha ao alterar cilindro.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // ============================================================
  // Formulário da Viagem
  // ============================================================
  if (formOpen) {
    const podeAdicionarItem = canAddItem && !viagem?.saida_fechada && !viagem?.entrada_fechada && viagem?.situacao !== "C";
    const podeRegistrarRetorno = viagem?.saida_fechada && !viagem?.entrada_fechada;

    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="viagem-cadastro-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => { setFormOpen(false); if (conn) loadList(conn); }} style={styles.iconBtn} hitSlop={12} testID="viagem-form-back">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
          <Text style={styles.headerTitle} numberOfLines={1}>
            {viagem ? `Viagem #${viagem.codigo} — ${viagem.situacao === "A" ? "Aberta" : viagem.situacao === "F" ? "Fechada" : "Cancelada"}` : "Nova Viagem"}
          </Text>
          {canGravar ? (
            <Pressable onPress={salvarCabecalho} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="viagem-gravar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : <View style={{ width: 40 }} />}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Veículo *</Text>
                  <Pressable onPress={abrirVeiculoPicker} style={styles.pickerBtn} testID="viagem-escolher-veiculo">
                    <Text style={styles.pickerBtnText} numberOfLines={1}>{veiculo ? veiculo.nome : "Selecionar veículo…"}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Tipo de Viagem</Text>
                  <View style={styles.pillRow}>
                    <Pressable onPress={() => setTipoViagem(0)} style={[styles.pillBtn, tipoViagem === 0 && styles.pillBtnSel]}>
                      <Text style={[styles.pillBtnText, tipoViagem === 0 && styles.pillBtnTextSel]}>Normal</Text>
                    </Pressable>
                    <Pressable onPress={() => setTipoViagem(1)} style={[styles.pillBtn, tipoViagem === 1 && styles.pillBtnSel]}>
                      <Text style={[styles.pillBtnText, tipoViagem === 1 && styles.pillBtnTextSel]}>Fábrica</Text>
                    </Pressable>
                  </View>
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Motorista</Text>
                  <SelectField value={motorista} onChange={(v) => setMotorista(v as string)} options={motoristaOptions} testID="viagem-motorista" modalTitle="Motorista" compactWeb />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Auxiliar</Text>
                  <SelectField value={ajudante} onChange={(v) => setAjudante(v as string)} options={auxiliarOptions} testID="viagem-ajudante" modalTitle="Auxiliar" compactWeb />
                </View>
              </View>

              <Text style={styles.label}>Descrição (Histórico)</Text>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} multiline testID="viagem-descricao" />
              <Text style={styles.label}>Observação</Text>
              <TextInput value={obs} onChangeText={setObs} style={styles.input} multiline testID="viagem-obs" />

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Saída</Text>
                  <WebDateField value={dataSaida} onChange={setDataSaida} disabled={!!viagem?.saida_fechada} testID="viagem-data-saida" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Hora Saída</Text>
                  <WebDateField value={horaSaida} onChange={setHoraSaida} type="time" disabled={!!viagem?.saida_fechada} testID="viagem-hora-saida" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Km Saída</Text>
                  <TextInput value={kmSaida} onChangeText={(v) => setKmSaida(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" editable={!viagem?.saida_fechada} testID="viagem-km-saida" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data Retorno</Text>
                  <WebDateField value={dataRetorno} onChange={setDataRetorno} disabled={!viagem?.saida_fechada || !!viagem?.entrada_fechada} testID="viagem-data-retorno" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Hora Retorno</Text>
                  <WebDateField value={horaRetorno} onChange={setHoraRetorno} type="time" disabled={!viagem?.saida_fechada || !!viagem?.entrada_fechada} testID="viagem-hora-retorno" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Km Retorno</Text>
                  <TextInput value={kmRetorno} onChangeText={(v) => setKmRetorno(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" editable={!!viagem?.saida_fechada && !viagem?.entrada_fechada} testID="viagem-km-retorno" />
                </View>
              </View>
            </View>

            {viagem ? (
              <View style={styles.toolbarRow}>
                {!viagem.saida_fechada ? (
                  <Pressable onPress={renumerar} disabled={busy} style={styles.secondaryBtn} testID="viagem-renumerar">
                    <Text style={styles.secondaryBtnText}>Renumerar Itens</Text>
                  </Pressable>
                ) : null}
                {canFecharSaida && !viagem.saida_fechada && viagem.situacao === "A" ? (
                  <Pressable onPress={fecharSaida} disabled={busy} style={styles.primaryBtn} testID="viagem-fechar-saida">
                    <Text style={styles.primaryBtnText}>Fechar Saída</Text>
                  </Pressable>
                ) : null}
                {canFecharEntrada && viagem.saida_fechada && !viagem.entrada_fechada && viagem.situacao === "A" ? (
                  <Pressable onPress={fecharEntrada} disabled={busy} style={styles.primaryBtn} testID="viagem-fechar-entrada">
                    <Text style={styles.primaryBtnText}>Fechar Entrada</Text>
                  </Pressable>
                ) : null}
                {canReabrir && (viagem.saida_fechada || viagem.entrada_fechada) && viagem.situacao === "A" ? (
                  <Pressable onPress={reabrir} disabled={busy} style={styles.secondaryBtn} testID="viagem-reabrir">
                    <Text style={styles.secondaryBtnText}>Reabrir Saída ou Retorno</Text>
                  </Pressable>
                ) : null}
                {canCancelar && !viagem.saida_fechada && viagem.situacao === "A" ? (
                  <Pressable onPress={cancelarViagem} disabled={busy} style={[styles.secondaryBtn, styles.dangerBtn]} testID="viagem-cancelar">
                    <Text style={styles.dangerBtnText}>Cancelar Viagem</Text>
                  </Pressable>
                ) : null}
              </View>
            ) : (
              <Text style={styles.hint}>Grave os dados da viagem para liberar o lançamento de itens.</Text>
            )}

            {viagem ? (
              <View style={styles.card}>
                <View style={styles.itensHeaderRow}>
                  <Text style={styles.sectionTitle}>Itens inclusos nesta viagem</Text>
                  {podeAdicionarItem ? (
                    <Pressable onPress={abrirNovoItem} style={styles.smallAddBtn} testID="viagem-add-item">
                      <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
                      <Text style={styles.smallAddBtnText}>Item</Text>
                    </Pressable>
                  ) : null}
                </View>

                {viagem.itens.length === 0 ? <Text style={styles.hint}>Nenhum item lançado.</Text> : null}
                {viagem.itens.map((it) => (
                  <Pressable
                    key={it.codigo}
                    onPress={() => (podeRegistrarRetorno ? abrirRetorno(it) : undefined)}
                    style={styles.itemRow}
                    testID={`viagem-item-${it.codigo}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText}>
                        #{it.ordem} · {it.cil_codigo} · Cap.{it.cil_capacidade} · Pressão {it.cil_pressao} · Padrão {it.cil_padrao}
                      </Text>
                      <Text style={styles.hint}>
                        {it.cliente_nome || `#${it.cliente}`} · Saída: {it.status_saida}
                        {it.status_retorno ? ` · Retorno: ${it.status_retorno}` : " · Retorno pendente"}
                      </Text>
                    </View>
                    {canAlterarCilindro && !it.status_retorno ? (
                      <Pressable onPress={() => { setAlterarItemCodigo(it.codigo); abrirCilindroPicker("alterar"); }} hitSlop={8} testID={`viagem-alterar-cilindro-${it.codigo}`}>
                        <Ionicons name="swap-horizontal-outline" size={18} color={colors.brandPrimary} />
                      </Pressable>
                    ) : null}
                    {canDelItem && !viagem.saida_fechada ? (
                      <Pressable onPress={() => excluirItem(it)} hitSlop={8} testID={`viagem-del-item-${it.codigo}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </Pressable>
                ))}
              </View>
            ) : null}
          </View>
        </ScrollView>

        {/* Picker Veículo */}
        <AppModal visible={veiculoPickerOpen} transparent animationType="slide" onRequestClose={() => setVeiculoPickerOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setVeiculoPickerOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Buscar Veículo</Text>
                <Pressable onPress={() => setVeiculoPickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <TextInput value={veiculoBusca} onChangeText={(v) => { setVeiculoBusca(v); buscarVeiculos(v); }} placeholder="Placa ou descrição…" placeholderTextColor={colors.muted} style={styles.input} autoFocus testID="veiculo-picker-busca" />
              {veiculoBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
                {veiculoResultados.map((v) => (
                  <Pressable key={v.codigo} onPress={() => selecionarVeiculo(v)} style={styles.gridRow} testID={`veiculo-picker-${v.codigo}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText}>{v.nome}</Text>
                      <Text style={styles.hint}>{v.sub}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
                {!veiculoBuscando && veiculoResultados.length === 0 ? <Text style={styles.hint}>Nenhum veículo encontrado.</Text> : null}
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>

        {/* Picker Cliente/Fornecedor */}
        <AppModal visible={clientePickerOpen} transparent animationType="slide" onRequestClose={() => setClientePickerOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setClientePickerOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>{tipoViagem === 1 ? "Buscar Fornecedor" : "Buscar Cliente"}</Text>
                <Pressable onPress={() => setClientePickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <TextInput value={clienteBusca} onChangeText={(v) => { setClienteBusca(v); buscarClientes(v); }} placeholder="Nome ou código…" placeholderTextColor={colors.muted} style={styles.input} autoFocus testID="cliente-picker-busca" />
              {clienteBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
                {clienteResultados.map((c) => (
                  <Pressable key={c.codigo} onPress={() => selecionarCliente(c)} style={styles.gridRow} testID={`cliente-picker-${c.codigo}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText} numberOfLines={1}>{c.nome}</Text>
                      <Text style={styles.hint}>#{c.codigo}{c.sub ? ` · ${c.sub}` : ""}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
                {!clienteBuscando && clienteResultados.length === 0 ? <Text style={styles.hint}>Nenhum resultado.</Text> : null}
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>

        {/* Picker Cilindro (compartilhado) */}
        <AppModal visible={cilindroPickerOpen} transparent animationType="slide" onRequestClose={() => setCilindroPickerOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setCilindroPickerOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Buscar Cilindro</Text>
                <Pressable onPress={() => setCilindroPickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <TextInput value={cilindroBusca} onChangeText={(v) => { setCilindroBusca(v); buscarCilindros(v); }} placeholder="Código, descrição ou grupo…" placeholderTextColor={colors.muted} style={styles.input} autoFocus testID="cilindro-picker-busca" />
              {cilindroBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
                {cilindroResultados.map((c) => (
                  <Pressable key={c.cod} onPress={() => selecionarCilindro(c)} style={styles.gridRow} testID={`cilindro-picker-${c.cod}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText} numberOfLines={1}>{c.descricao || c.codigo}</Text>
                      <Text style={styles.hint}>{c.codigo} · Cap.{c.capacidade} · Pressão {c.pressao} · Padrão {c.padrao}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
                {!cilindroBuscando && cilindroResultados.length === 0 ? <Text style={styles.hint}>Nenhum cilindro encontrado.</Text> : null}
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>

        {/* Modal Adicionar Item */}
        <AppModal visible={itemModalOpen} transparent animationType="slide" onRequestClose={() => setItemModalOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setItemModalOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact, styles.slideCardTall]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Cadastrar Item</Text>
                <Pressable onPress={() => setItemModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 480 }}>
                <Text style={styles.label}>Destinatário ({tipoViagem === 1 ? "Fornecedor" : "Cliente"}) *</Text>
                <Pressable onPress={abrirClientePicker} style={styles.pickerBtn} testID="item-escolher-cliente">
                  <Text style={styles.pickerBtnText} numberOfLines={1}>{itemCliente ? itemCliente.nome : "Selecionar…"}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <Text style={styles.label}>Cilindro *</Text>
                <Pressable onPress={() => abrirCilindroPicker("item")} style={styles.pickerBtn} testID="item-escolher-cilindro">
                  <Text style={styles.pickerBtnText} numberOfLines={1}>
                    {itemCilindro ? `${itemCilindro.codigo} · Cap.${itemCilindro.capacidade} · Pressão ${itemCilindro.pressao} · Padrão ${itemCilindro.padrao}` : "Selecionar…"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Número de Série (opcional)</Text>
                    <TextInput value={itemNumeroSerie} onChangeText={setItemNumeroSerie} style={styles.input} testID="item-numero-serie" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Status Saída *</Text>
                    <SelectField value={itemStatus} onChange={(v) => setItemStatus(v as string)} options={situacaoItemOptions} testID="item-status-saida" modalTitle="Status" compactWeb />
                  </View>
                </View>

                <View style={styles.rowFields}>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Doc. Saída</Text>
                    <TextInput value={itemDocSaida} onChangeText={(v) => setItemDocSaida(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="item-doc-saida" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>O.S.</Text>
                    <TextInput value={itemOsSaida} onChangeText={setItemOsSaida} style={styles.input} testID="item-os-saida" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Carga</Text>
                    <View style={styles.pillRow}>
                      <Pressable onPress={() => setItemCarga("CHEIO")} style={[styles.pillBtn, itemCarga === "CHEIO" && styles.pillBtnSel]}>
                        <Text style={[styles.pillBtnText, itemCarga === "CHEIO" && styles.pillBtnTextSel]}>Cheio</Text>
                      </Pressable>
                      <Pressable onPress={() => setItemCarga("VAZIO")} style={[styles.pillBtn, itemCarga === "VAZIO" && styles.pillBtnSel]}>
                        <Text style={[styles.pillBtnText, itemCarga === "VAZIO" && styles.pillBtnTextSel]}>Vazio</Text>
                      </Pressable>
                    </View>
                  </View>
                </View>

                <Text style={styles.label}>Observação</Text>
                <TextInput value={itemObs} onChangeText={setItemObs} style={styles.input} multiline testID="item-obs" />

                <View style={styles.modalActionsRow}>
                  <Pressable onPress={salvarNovoItem} disabled={itemSaving} style={styles.primaryBtn} testID="item-gravar">
                    {itemSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Adicionar Item</Text>}
                  </Pressable>
                </View>
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>

        {/* Modal Registrar Retorno */}
        <AppModal visible={retornoModalOpen} transparent animationType="slide" onRequestClose={() => setRetornoModalOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setRetornoModalOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact, styles.slideCardTall]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Registrar Retorno do Item</Text>
                <Pressable onPress={() => setRetornoModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 480 }}>
                <Text style={styles.label}>Cilindro de Retorno *</Text>
                <Pressable onPress={() => abrirCilindroPicker("retorno")} style={styles.pickerBtn} testID="retorno-escolher-cilindro">
                  <Text style={styles.pickerBtnText} numberOfLines={1}>
                    {retornoCilindro ? `${retornoCilindro.codigo} · Cap.${retornoCilindro.capacidade} · Pressão ${retornoCilindro.pressao} · Padrão ${retornoCilindro.padrao}` : "Selecionar…"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <View style={styles.rowFields}>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Número de Série de Retorno</Text>
                    <TextInput value={retornoNumeroSerie} onChangeText={setRetornoNumeroSerie} style={styles.input} testID="retorno-numero-serie" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Status Retorno *</Text>
                    <SelectField value={retornoStatus} onChange={(v) => setRetornoStatus(v as string)} options={situacaoItemOptions} testID="retorno-status" modalTitle="Status" compactWeb />
                  </View>
                </View>

                <View style={styles.rowFields}>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Nº Documento</Text>
                    <TextInput value={retornoNf} onChangeText={(v) => setRetornoNf(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="retorno-nf" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>O.S.</Text>
                    <TextInput value={retornoOs} onChangeText={setRetornoOs} style={styles.input} testID="retorno-os" />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Carga</Text>
                    <View style={styles.pillRow}>
                      <Pressable onPress={() => setRetornoCarga("CHEIO")} style={[styles.pillBtn, retornoCarga === "CHEIO" && styles.pillBtnSel]}>
                        <Text style={[styles.pillBtnText, retornoCarga === "CHEIO" && styles.pillBtnTextSel]}>Cheio</Text>
                      </Pressable>
                      <Pressable onPress={() => setRetornoCarga("VAZIO")} style={[styles.pillBtn, retornoCarga === "VAZIO" && styles.pillBtnSel]}>
                        <Text style={[styles.pillBtnText, retornoCarga === "VAZIO" && styles.pillBtnTextSel]}>Vazio</Text>
                      </Pressable>
                    </View>
                  </View>
                </View>

                <Text style={styles.label}>Observação</Text>
                <TextInput value={retornoObs} onChangeText={setRetornoObs} style={styles.input} multiline testID="retorno-obs" />

                <View style={styles.modalActionsRow}>
                  <Pressable onPress={salvarRetorno} disabled={retornoSaving} style={styles.primaryBtn} testID="retorno-gravar">
                    {retornoSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Gravar Retorno</Text>}
                  </Pressable>
                </View>
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>
      </SafeAreaView>
    );
  }

  // ============================================================
  // Lista / Consulta
  // ============================================================
  if (!canOpen) {
    return (
      <LockedView title="Sem permissão" message="Você não tem permissão para acessar Viagens." testID="viagem-cadastro-no-perm" />
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="viagem-cadastro-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Viagens</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.listShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={(v) => { setSearch(v); if (conn) loadList(conn, v); }}
            placeholder="Buscar por código da viagem…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            keyboardType="number-pad"
            testID="viagem-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma viagem cadastrada.</Text> : null}
          {items.map((it) => (
            <Pressable key={it.codigo} onPress={() => carregarViagem(it.codigo)} style={styles.row} testID={`viagem-${it.codigo}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>Viagem #{it.codigo} — {it.placa || "sem veículo"}</Text>
                <Text style={styles.rowSub}>
                  {it.tipo_viagem === 1 ? "Fábrica" : "Normal"} · {it.situacao === "A" ? "Aberta" : it.situacao === "F" ? "Fechada" : "Cancelada"}
                  {it.motorista_nome ? ` · ${it.motorista_nome}` : ""}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {canGravar ? (
        <Pressable onPress={openNew} style={styles.fab} testID="viagem-nova">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 160 },
  colTiny: { width: 110 },

  toolbarRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  secondaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  dangerBtn: { backgroundColor: colors.surface, borderColor: colors.error },
  dangerBtnText: { fontSize: 13, fontWeight: "600", color: colors.error },

  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  itensHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  smallAddBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  smallAddBtnText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "600" },
  itemRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, paddingVertical: 10, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, marginBottom: 6 },
  gridRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 10, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: "transparent", marginBottom: 6 },
  gridRowText: { fontSize: 13, color: colors.onSurface },

  pickerBtn: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11 },
  pickerBtnText: { flex: 1, fontSize: 14, color: colors.onSurface },
  pillRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },
  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md, marginBottom: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  slideBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  slideCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "85%" },
  slideCardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  slideCardTall: { maxHeight: "90%" },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  slideTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
});
