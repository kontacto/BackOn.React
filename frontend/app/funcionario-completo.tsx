import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext, AuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type TabKey = "dados" | "comissoes" | "horarios" | "ausencias" | "especialidades";

const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "dados", label: "Dados", icon: "person-outline" },
  { key: "comissoes", label: "Comissões", icon: "cash-outline" },
  { key: "horarios", label: "Horários", icon: "time-outline" },
  { key: "ausencias", label: "Ausências", icon: "calendar-outline" },
  { key: "especialidades", label: "Especialidades", icon: "ribbon-outline" },
];

const TIPO_COMISSAO_OPTS: SelectOption[] = [
  { value: "C", label: "Coletivo" },
  { value: "E", label: "Especial" },
  { value: "F", label: "Função" },
  { value: "G", label: "Geral" },
  { value: "I", label: "Individual" },
  { value: "S", label: "Sem Comissão" },
];

const SEXO_OPTS: SelectOption[] = [
  { value: "M", label: "Masculino" },
  { value: "F", label: "Feminino" },
];

const DIAS_SEMANA = [
  { dia: 1, label: "Domingo" },
  { dia: 2, label: "Segunda-Feira" },
  { dia: 3, label: "Terça-Feira" },
  { dia: 4, label: "Quarta-Feira" },
  { dia: 5, label: "Quinta-Feira" },
  { dia: 6, label: "Sexta-Feira" },
  { dia: 7, label: "Sábado" },
];

type HorarioDia = {
  ativo: boolean; dispIni: string; dispFim: string; intervalo1: string; pausaIni: string; pausaFim: string; encaixe: string;
};
const horarioVazio = (): HorarioDia => ({ ativo: false, dispIni: "", dispFim: "", intervalo1: "", pausaIni: "", pausaFim: "", encaixe: "" });

type Ausencia = {
  codigo_funcionarios_ausencias: number; data_ini: string; data_fim: string;
  hora_ini: string; hora_fim: string; intervalo1: number; obs: string;
};

type ComissaoExcecao = {
  cod_comissao_excecao: number; item: string; tipo: "V" | "E" | "A"; tipo_ps: "P" | "S"; comissao: number; descricao: string;
};

const formatHora = (v: string) => {
  const digits = v.replace(/[^0-9]/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
};

const tipoExcecaoLabel = (t: "V" | "E" | "A") => (t === "V" ? "Vendedor" : t === "E" ? "Executor" : "Atendente");

// Cadastro > Funcionários — cadastro completo (tabela `funcionarios` + sub-
// tabelas). Legado: FrmManPro ("Manutenção de Funcionários"). Ver
// `funcionarios_service.py` para a lista completa de itens do legado
// deliberadamente fora de escopo (fotografia/webcam, anexos, layouts,
// posto/tag, campos de folha de pagamento já escondidos no próprio .frm,
// `funcionarios_dia_trab` [código morto] e `funcionarios_agenda` [outra
// funcionalidade]).
//
// Simplificação deliberada: Área de Atuação / Área de Estoque / Carteira de
// Clientes / Especialidades são, no legado, ou já listboxes de checkbox
// simples (Areas/Area/Carteiras) ou um transfer-list de 2 colunas com
// duplo-clique (Especial1/Especial2). Aqui todas viram uma única lista com
// checkbox — resultado funcional idêntico (quais itens ficam marcados),
// sem depender de duplo-clique entre 2 colunas.
export default function FuncionarioCompletoScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Funcionários está disponível apenas no web."
        testID="funcionario-completo-web-only"
      />
    );
  }

  return <FuncionarioCompletoWeb router={router} can={can} />;
}

function FuncionarioCompletoWeb({
  router,
  can,
}: {
  router: ReturnType<typeof useRouter>;
  can: (perm: string) => boolean;
}) {
  const params = useLocalSearchParams<{ codigo?: string }>();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [codigo, setCodigo] = useState<number | null>(params.codigo ? parseInt(String(params.codigo), 10) : null);
  const editing = codigo != null;
  const [tab, setTab] = useState<TabKey>("dados");
  const [conn, setConn] = useState<Connection | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);

  const [situacaoOptions, setSituacaoOptions] = useState<SelectOption[]>([]);
  const [funcaoOptions, setFuncaoOptions] = useState<SelectOption[]>([]);
  const [cargoOptions, setCargoOptions] = useState<SelectOption[]>([]);
  const [areaOptions, setAreaOptions] = useState<SelectOption[]>([]);
  const [areaAtuacaoOptions, setAreaAtuacaoOptions] = useState<SelectOption[]>([]);
  const [especialidadeOptions, setEspecialidadeOptions] = useState<SelectOption[]>([]);
  const [vendedorOptions, setVendedorOptions] = useState<SelectOption[]>([]);

  // ---- Cabeçalho / Dados Principais ----
  const [nomeGuerra, setNomeGuerra] = useState("");
  const [situacao, setSituacao] = useState<string | null>("A");
  const [nome, setNome] = useState("");
  const [codFuncao, setCodFuncao] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [liberarListaNegra, setLiberarListaNegra] = useState(false);
  const [liberarLimiteExcedido, setLiberarLimiteExcedido] = useState(false);
  const [areasEstoque, setAreasEstoque] = useState<number[]>([]);
  const [areasAtuacao, setAreasAtuacao] = useState<number[]>([]);

  // ---- Aba Dados ----
  const [admissao, setAdmissao] = useState<string | null>(null);
  const [cpfProf, setCpfProf] = useState("");
  const [identProf, setIdentProf] = useState("");
  const [cartProf, setCartProf] = useState("");
  const [dataNasc, setDataNasc] = useState<string | null>(null);
  const [sexoProf, setSexoProf] = useState<string | null>(null);
  const [codigoDep, setCodigoDep] = useState("");
  const [docespecial, setDocespecial] = useState("");
  const [numespecial, setNumespecial] = useState("");
  const [conselho, setConselho] = useState("");
  const [numconselho, setNumconselho] = useState("");
  const [codcargo, setCodcargo] = useState<number | null>(null);
  const [cepProf, setCepProf] = useState("");
  const [bairrProf, setBairrProf] = useState("");
  const [endereco, setEndereco] = useState("");
  const [cidProf, setCidProf] = useState("");
  const [estProf, setEstProf] = useState("");
  const [telProf, setTelProf] = useState("");
  const [controlaCarteira, setControlaCarteira] = useState(false);
  const [carteiras, setCarteiras] = useState<number[]>([]);

  // ---- Aba Comissões ----
  const [tipoComissao, setTipoComissao] = useState<string | null>("S");
  const [comissaop, setComissaop] = useState("0");
  const [comissaos, setComissaos] = useState("0");
  const [prioridadeVendedor, setPrioridadeVendedor] = useState(false);
  const [tipoComissaoE, setTipoComissaoE] = useState<string | null>("S");
  const [comissaopE, setComissaopE] = useState("0");
  const [comissaosE, setComissaosE] = useState("0");
  const [prioridadeExecutor, setPrioridadeExecutor] = useState(false);
  const [tipoComissaoA, setTipoComissaoA] = useState<string | null>("S");
  const [comissaopA, setComissaopA] = useState("0");
  const [comissaosA, setComissaosA] = useState("0");
  const [prioridadeAtendente, setPrioridadeAtendente] = useState(false);
  const [descontaComissao, setDescontaComissao] = useState(false);
  const [comissaoExcecoes, setComissaoExcecoes] = useState<ComissaoExcecao[]>([]);
  const [excecaoItem, setExcecaoItem] = useState("");
  const [excecaoTipo, setExcecaoTipo] = useState<"V" | "E" | "A">("V");
  const [excecaoComissao, setExcecaoComissao] = useState("");
  const [excecaoSaving, setExcecaoSaving] = useState(false);

  // ---- Aba Horários ----
  const [horarios, setHorarios] = useState<HorarioDia[]>(() => DIAS_SEMANA.map(horarioVazio));

  // ---- Aba Ausências ----
  const [ausencias, setAusencias] = useState<Ausencia[]>([]);
  const [ausPeriodoIni, setAusPeriodoIni] = useState<string | null>(null);
  const [ausPeriodoFim, setAusPeriodoFim] = useState<string | null>(null);
  const [ausHoraIni, setAusHoraIni] = useState("");
  const [ausHoraFim, setAusHoraFim] = useState("");
  const [ausIntervalo, setAusIntervalo] = useState("0");
  const [ausMotivo, setAusMotivo] = useState("");
  const [ausSaving, setAusSaving] = useState(false);

  // ---- Aba Especialidades ----
  const [especialidades, setEspecialidades] = useState<number[]>([]);
  const [especialidadesModalOpen, setEspecialidadesModalOpen] = useState(false);

  const loadLookups = useCallback(async (c: Connection) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rSit, rFunc, rCargo, rArea, rAreaAt, rEsp] = await Promise.all([
        fetch(`${base}/api/tabelas/situacao?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/funcoes?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/cargos?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/area?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/area-atuacao?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/especialidades?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rSit?.success) setSituacaoOptions((rSit.items || []).map((i: any) => ({ value: i.codigo, label: `${i.codigo} ${i.descricao}` })));
      if (rFunc?.success) setFuncaoOptions((rFunc.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rCargo?.success) setCargoOptions((rCargo.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rArea?.success) setAreaOptions((rArea.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rAreaAt?.success) setAreaAtuacaoOptions((rAreaAt.items || []).map((i: any) => ({ value: i.codigo ?? i.area, label: i.descricao })));
      if (rEsp?.success) setEspecialidadeOptions((rEsp.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  const loadVendedores = useCallback(async (c: Connection, excluir: number | null) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}${excluir ? `&excluir=${excluir}` : ""}`;
    try {
      const r = await fetch(`${base}/api/funcionarios-cadastro/vendedores?${qs}`).then((x) => x.json());
      if (r?.success) setVendedorOptions((r.items || []).map((i: any) => ({ value: i.codigo, label: i.nome })));
    } catch {
      setVendedorOptions([]);
    }
  }, []);

  const carregarDetalhe = useCallback(async (c: Connection, cod: number) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/funcionarios-cadastro/${cod}?${qs}`);
      const j = await r.json();
      if (!j?.success) {
        fb.showError(j?.message || "Erro ao carregar funcionário.");
        router.back();
        return;
      }
      const d = j.funcionario;
      setNomeGuerra(d.nome_guerra || "");
      setSituacao(d.situacao || "A");
      setNome(d.nome || "");
      setCodFuncao(d.cod_funcao || null);
      setEmail(d.email || "");
      setLiberarListaNegra(!!d.liberar_pedido_lista_negra);
      setLiberarLimiteExcedido(!!d.liberar_pedido_limite_excedido);
      setAreasEstoque(d.areas_estoque || []);
      setAreasAtuacao(d.areas_atuacao || []);

      setAdmissao(d.admissao || null);
      setCpfProf(d.cpf_prof || "");
      setIdentProf(d.ident_prof || "");
      setCartProf(d.cart_prof || "");
      setDataNasc(d.data_nasc || null);
      setSexoProf(d.sexo_prof || null);
      setCodigoDep(d.CODIGO_DEP || "");
      setDocespecial(d.docespecial != null ? String(d.docespecial) : "");
      setNumespecial(d.numespecial || "");
      setConselho(d.conselho || "");
      setNumconselho(d.numconselho || "");
      setCodcargo(d.codcargo ?? null);
      setCepProf(d.cep_prof || "");
      setBairrProf(d.bairr_prof || "");
      setEndereco(d.endereco || "");
      setCidProf(d.cid_prof || "");
      setEstProf(d.est_prof || "");
      setTelProf(d.tel_prof || "");
      setControlaCarteira(!!d.Controla_Carteira);
      setCarteiras(d.carteiras || []);

      setTipoComissao(d.tipo_comissao || "S");
      setComissaop(String(d.comissaop ?? 0));
      setComissaos(String(d.comissaos ?? 0));
      setPrioridadeVendedor(!!d.COMISSAO_PRIORIDADE_VENDEDOR);
      setTipoComissaoE(d.tipo_comissao_e || "S");
      setComissaopE(String(d.comissaop_e ?? 0));
      setComissaosE(String(d.comissaos_e ?? 0));
      setPrioridadeExecutor(!!d.COMISSAO_PRIORIDADE_EXECUTOR);
      setTipoComissaoA(d.tipo_comissao_a || "S");
      setComissaopA(String(d.comissaop_a ?? 0));
      setComissaosA(String(d.comissaos_a ?? 0));
      setPrioridadeAtendente(!!d.COMISSAO_PRIORIDADE_ATENDENTE);
      setDescontaComissao(!!d.DESCONTA_DESCARTAVEIS);
      setComissaoExcecoes(d.comissao_excecoes || []);

      const novoHorarios = DIAS_SEMANA.map(horarioVazio);
      for (const h of d.horarios || []) {
        const idx = novoHorarios.findIndex((_, i) => DIAS_SEMANA[i].dia === h.dia);
        if (idx >= 0) {
          novoHorarios[idx] = {
            ativo: true,
            dispIni: h.disp_ini || "", dispFim: h.disp_fim || "",
            intervalo1: h.intervalo1 != null ? String(h.intervalo1) : "",
            pausaIni: h.pausa_ini || "", pausaFim: h.pausa_fim || "",
            encaixe: h.encaixe != null ? String(h.encaixe) : "",
          };
        }
      }
      setHorarios(novoHorarios);

      setAusencias(d.ausencias || []);
      setEspecialidades(d.especialidades || []);

      loadVendedores(c, cod);
    } catch (e) {
      fb.showError(`Erro ao carregar: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [fb, router, loadVendedores]);

  useEffect(() => {
    (async () => {
      setLoadingInit(true);
      const session = await getSession();
      if (!session) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === session.empresa) ?? null;
      setConn(c);
      if (!c) { fb.showError("Conexão não encontrada."); setLoadingInit(false); return; }
      await loadLookups(c);
      if (codigo != null) {
        await carregarDetalhe(c, codigo);
      } else {
        loadVendedores(c, null);
      }
      setLoadingInit(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleInList = (list: number[], setList: (v: number[]) => void, id: number) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  };

  const handleSave = async () => {
    if (!conn) return;
    if (!nomeGuerra.trim()) { fb.showWarning("Preencha CodiNome Apropriadamente"); return; }
    if (!nome.trim()) { fb.showWarning("Preencha Nome Apropriadamente"); return; }
    if (!codFuncao) { fb.showWarning("Preencha a Função Apropriadamente"); return; }

    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, ...auditCtx,
        codigo,
        nome_guerra: nomeGuerra.trim(), situacao, nome: nome.trim(), cod_funcao: codFuncao,
        email: email.trim(), liberar_pedido_lista_negra: liberarListaNegra, liberar_pedido_limite_excedido: liberarLimiteExcedido,
        admissao, cpf_prof: cpfProf.trim(), ident_prof: identProf.trim(), cart_prof: cartProf.trim(),
        data_nasc: dataNasc, sexo_prof: sexoProf,
        codigo_dep: codigoDep.trim(), docespecial: docespecial.trim() ? parseInt(docespecial, 10) : null,
        numespecial: numespecial.trim(), conselho: conselho.trim(), numconselho: numconselho.trim(),
        codcargo, cep_prof: cepProf.trim(), bairr_prof: bairrProf.trim(), endereco: endereco.trim(),
        cid_prof: cidProf.trim(), est_prof: estProf.trim().toUpperCase(), tel_prof: telProf.trim(),
        controla_carteira: controlaCarteira,
        tipo_comissao: tipoComissao, comissaop: parseFloat(comissaop || "0"), comissaos: parseFloat(comissaos || "0"),
        comissao_prioridade_vendedor: prioridadeVendedor,
        tipo_comissao_e: tipoComissaoE, comissaop_e: parseFloat(comissaopE || "0"), comissaos_e: parseFloat(comissaosE || "0"),
        comissao_prioridade_executor: prioridadeExecutor,
        tipo_comissao_a: tipoComissaoA, comissaop_a: parseFloat(comissaopA || "0"), comissaos_a: parseFloat(comissaosA || "0"),
        comissao_prioridade_atendente: prioridadeAtendente,
        desconta_comissao: descontaComissao,
        areas_estoque: areasEstoque, areas_atuacao: areasAtuacao, carteiras, especialidades,
        horarios: horarios
          .map((h, i) => ({ ...h, dia: DIAS_SEMANA[i].dia }))
          .filter((h) => h.ativo)
          .map((h) => ({
            dia: h.dia, disp_ini: h.dispIni || null, disp_fim: h.dispFim || null,
            intervalo1: h.intervalo1 ? parseInt(h.intervalo1, 10) : 0,
            pausa_ini: h.pausaIni || null, pausa_fim: h.pausaFim || null,
            encaixe: h.encaixe ? parseInt(h.encaixe, 10) : 0,
          })),
      };
      const r = await fetch(`${base}/api/funcionarios-cadastro`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Funcionário gravado.");
        if (!codigo && j.codigo) { setCodigo(j.codigo); loadVendedores(conn, j.codigo); }
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    if (!conn || !codigo) return;
    Alert.alert("Excluir Funcionário", `Confirma a exclusão de "${nomeGuerra}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/funcionarios-cadastro/${codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); router.back(); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) {
            fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
          }
        },
      },
    ]);
  };

  const adicionarAusencia = async () => {
    if (!conn || !codigo) return;
    if (!ausPeriodoIni || !ausPeriodoFim) { fb.showWarning("Preencha início e término corretamente!"); return; }
    if (!ausHoraIni || !ausHoraFim) { fb.showWarning("Preencha início e término corretamente!"); return; }
    if (!ausMotivo.trim()) { fb.showWarning("Preencha o motivo corretamente!"); return; }
    setAusSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/funcionarios-cadastro/${codigo}/ausencias`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          data_ini: ausPeriodoIni, data_fim: ausPeriodoFim, hora_ini: ausHoraIni, hora_fim: ausHoraFim,
          intervalo1: ausIntervalo ? parseInt(ausIntervalo, 10) : 0, obs: ausMotivo.trim(),
        }),
      });
      const j = await r.json();
      if (j?.success) {
        setAusencias((prev) => [{
          codigo_funcionarios_ausencias: j.codigo, data_ini: ausPeriodoIni, data_fim: ausPeriodoFim,
          hora_ini: ausHoraIni, hora_fim: ausHoraFim, intervalo1: ausIntervalo ? parseInt(ausIntervalo, 10) : 0, obs: ausMotivo.trim(),
        }, ...prev]);
        setAusPeriodoIni(null); setAusPeriodoFim(null); setAusHoraIni(""); setAusHoraFim(""); setAusIntervalo("0"); setAusMotivo("");
        fb.showSuccess("Ausência registrada.");
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAusSaving(false);
    }
  };

  const excluirAusencia = (a: Ausencia) => {
    if (!conn) return;
    Alert.alert("Excluir ausência?", "", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          const base = conn.api.replace(/\/+$/, "");
          const r = await fetch(`${base}/api/funcionarios-cadastro/ausencias/${a.codigo_funcionarios_ausencias}/excluir`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
          });
          const j = await r.json();
          if (j?.success) setAusencias((prev) => prev.filter((x) => x.codigo_funcionarios_ausencias !== a.codigo_funcionarios_ausencias));
          else fb.showError(j?.message || "Falha ao excluir.");
        },
      },
    ]);
  };

  const gravarExcecao = async () => {
    if (!conn || !codigo) return;
    if (!excecaoItem.trim()) { fb.showWarning("Preencha o código do produto ou serviço!"); return; }
    const comissaoNum = parseFloat(excecaoComissao || "0");
    if (!comissaoNum || comissaoNum <= 0) { fb.showWarning("Preencha a Comissão Apropriadamente"); return; }
    setExcecaoSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/funcionarios-cadastro/${codigo}/comissao-excecao`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, item: excecaoItem.trim(), tipo: excecaoTipo, comissao: comissaoNum }),
      });
      const j = await r.json();
      if (j?.success) {
        await carregarDetalhe(conn, codigo);
        setExcecaoItem(""); setExcecaoComissao("");
        fb.showSuccess(j.message || "Exceção gravada.");
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExcecaoSaving(false);
    }
  };

  const excluirExcecao = (ex: ComissaoExcecao) => {
    if (!conn) return;
    Alert.alert("Excluir esta exceção?", "", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          const base = conn.api.replace(/\/+$/, "");
          const r = await fetch(`${base}/api/funcionarios-cadastro/comissao-excecao/${ex.cod_comissao_excecao}/excluir`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
          });
          const j = await r.json();
          if (j?.success) setComissaoExcecoes((prev) => prev.filter((x) => x.cod_comissao_excecao !== ex.cod_comissao_excecao));
          else fb.showError(j?.message || "Falha ao excluir.");
        },
      },
    ]);
  };

  if (loadingInit) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  const canSave = can("FUNCIONARIOS.GRAVAR");
  const canDelete = can("FUNCIONARIOS.EXCLUIR");
  const canEspecialidades = can("FUNCIONARIOS.ESPECIALIDADE");

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="funcionario-completo-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12} testID="funcionario-completo-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>{editing ? `Funcionário — ${nomeGuerra}` : "Novo Funcionário"}</Text>
        {canSave ? (
          <Pressable onPress={handleSave} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.7 }]} hitSlop={8} testID="funcionario-completo-salvar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <><Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} /><Text style={styles.saveLabel}>Gravar</Text></>
            )}
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {/* Cabeçalho sempre visível */}
          <View style={styles.card}>
            <View style={styles.formGrid}>
              <Field label="Codinome *" style={styles.colHalf}>
                <TextInput value={nomeGuerra} onChangeText={(v) => setNomeGuerra(v.toUpperCase())} style={[styles.input, editing && styles.inputDisabled]} editable={!editing} maxLength={15} autoCapitalize="characters" testID="func-nome-guerra" />
              </Field>
              <Field label="Situação" style={styles.colHalf}>
                <SelectField value={situacao} onChange={(v) => setSituacao(v as string)} options={situacaoOptions} testID="func-situacao" modalTitle="Situação" compactWeb />
              </Field>
              <Field label="Nome Completo *" style={styles.fullWidth}>
                <TextInput value={nome} onChangeText={(v) => setNome(v.toUpperCase())} style={styles.input} maxLength={40} autoCapitalize="characters" testID="func-nome" />
              </Field>
              <Field label="Função do Sistema *" style={styles.colHalf}>
                <SelectField value={codFuncao} onChange={(v) => setCodFuncao(v as string)} options={funcaoOptions} testID="func-funcao" modalTitle="Função do Sistema" compactWeb />
              </Field>
              <Field label="Email" style={styles.colHalf}>
                <TextInput value={email} onChangeText={setEmail} style={styles.input} keyboardType="email-address" autoCapitalize="none" testID="func-email" />
              </Field>
            </View>

            <View style={styles.switchRow}>
              <Switch value={liberarListaNegra} onValueChange={setLiberarListaNegra} testID="func-libera-lista-negra" />
              <Text style={styles.switchLabel}>Libera Pedido de Cliente na Lista Negra</Text>
            </View>
            <View style={styles.switchRow}>
              <Switch value={liberarLimiteExcedido} onValueChange={setLiberarLimiteExcedido} testID="func-libera-limite" />
              <Text style={styles.switchLabel}>Libera Cliente com Limite de Crédito Excedido</Text>
            </View>

            <View style={styles.formGrid}>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Área(s) de Atuação</Text>
                <ChecklistBox options={areaAtuacaoOptions} selected={areasAtuacao} onToggle={(id) => toggleInList(areasAtuacao, setAreasAtuacao, id)} testIDPrefix="func-area-atuacao" />
              </View>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Área(s) de Estoque</Text>
                <ChecklistBox options={areaOptions} selected={areasEstoque} onToggle={(id) => toggleInList(areasEstoque, setAreasEstoque, id)} testIDPrefix="func-area-estoque" />
              </View>
            </View>
          </View>

          {/* Abas */}
          <View style={styles.tabBar}>
            {TABS.map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable key={t.key} onPress={() => setTab(t.key)} style={[styles.tabBtn, sel && styles.tabBtnSel]} testID={`func-tab-${t.key}`}>
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {tab === "dados" ? (
            <View style={styles.card} testID="func-tab-content-dados">
              <View style={styles.formGrid}>
                <Field label="Admissão" style={styles.colHalf}><DateField value={admissao} onChange={setAdmissao} testID="func-admissao" /></Field>
                <Field label="Data Nasc." style={styles.colHalf}><DateField value={dataNasc} onChange={setDataNasc} testID="func-data-nasc" /></Field>

                <Field label="CPF" style={styles.colHalf}><TextInput value={cpfProf} onChangeText={(v) => setCpfProf(v.replace(/[^0-9]/g, ""))} style={styles.input} maxLength={11} keyboardType="number-pad" testID="func-cpf" /></Field>
                <Field label="Identidade" style={styles.colHalf}><TextInput value={identProf} onChangeText={setIdentProf} style={styles.input} maxLength={10} testID="func-identidade" /></Field>

                <Field label="Carteira Profissional" style={styles.colHalf}><TextInput value={cartProf} onChangeText={setCartProf} style={styles.input} maxLength={13} testID="func-carteira-prof" /></Field>
                <Field label="Sexo" style={styles.colHalf}><SelectField value={sexoProf} onChange={(v) => setSexoProf(v as string)} options={SEXO_OPTS} allowClear testID="func-sexo" modalTitle="Sexo" compactWeb /></Field>

                <Field label="Cód DP" style={styles.colHalf}><TextInput value={codigoDep} onChangeText={setCodigoDep} style={styles.input} maxLength={50} testID="func-cod-dp" /></Field>
                <Field label="Doc Especial" style={styles.colHalf}><TextInput value={docespecial} onChangeText={(v) => setDocespecial(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="func-doc-especial" /></Field>

                <Field label="Número Especial" style={styles.colHalf}><TextInput value={numespecial} onChangeText={setNumespecial} style={styles.input} maxLength={15} testID="func-num-especial" /></Field>
                <Field label="Conselho" style={styles.colHalf}><TextInput value={conselho} onChangeText={setConselho} style={styles.input} maxLength={15} testID="func-conselho" /></Field>

                <Field label="Num Conselho" style={styles.colHalf}><TextInput value={numconselho} onChangeText={setNumconselho} style={styles.input} maxLength={15} testID="func-num-conselho" /></Field>
                <Field label="Cargo" style={styles.colHalf}><SelectField value={codcargo} onChange={(v) => setCodcargo(v as number)} options={cargoOptions} allowClear testID="func-cargo" modalTitle="Cargo" compactWeb /></Field>

                <Field label="CEP" style={styles.colHalf}>
                  <TextInput
                    value={cepProf}
                    onChangeText={(v) => setCepProf(v.replace(/[^0-9]/g, ""))}
                    onBlur={async () => {
                      const cep = cepProf.replace(/[^0-9]/g, "");
                      if (cep.length !== 8) return;
                      try {
                        const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
                        const j = await r.json();
                        if (!j?.erro) {
                          setEndereco((j.logradouro || "").toUpperCase());
                          setBairrProf((j.bairro || "").toUpperCase());
                          setCidProf((j.localidade || "").toUpperCase());
                          setEstProf((j.uf || "").toUpperCase());
                        }
                      } catch {
                        // silencioso — CEP fica só como digitado
                      }
                    }}
                    style={styles.input}
                    maxLength={8}
                    keyboardType="number-pad"
                    testID="func-cep"
                  />
                </Field>
                <Field label="Bairro" style={styles.colHalf}><TextInput value={bairrProf} onChangeText={(v) => setBairrProf(v.toUpperCase())} style={styles.input} maxLength={50} testID="func-bairro" /></Field>

                <Field label="Endereço" style={styles.fullWidth}><TextInput value={endereco} onChangeText={(v) => setEndereco(v.toUpperCase())} style={styles.input} maxLength={60} testID="func-endereco" /></Field>

                <Field label="Cidade" style={styles.colHalf}><TextInput value={cidProf} onChangeText={(v) => setCidProf(v.toUpperCase())} style={styles.input} maxLength={20} testID="func-cidade" /></Field>
                <Field label="Estado" style={styles.colHalf}><TextInput value={estProf} onChangeText={(v) => setEstProf(v.toUpperCase())} style={styles.input} maxLength={2} autoCapitalize="characters" testID="func-estado" /></Field>

                <Field label="Telefone" style={styles.fullWidth}><TextInput value={telProf} onChangeText={setTelProf} style={styles.input} maxLength={15} testID="func-telefone" /></Field>
              </View>

              <View style={styles.switchRow}>
                <Switch value={controlaCarteira} onValueChange={setControlaCarteira} testID="func-controla-carteira" />
                <Text style={styles.switchLabel}>Controla Carteira de Clientes</Text>
              </View>
              {controlaCarteira ? (
                <ChecklistBox options={vendedorOptions} selected={carteiras} onToggle={(id) => toggleInList(carteiras, setCarteiras, id)} testIDPrefix="func-carteira" />
              ) : null}
            </View>
          ) : null}

          {tab === "comissoes" ? (
            <View style={styles.card} testID="func-tab-content-comissoes">
              <ComissaoLinha
                titulo="Vendedor" pctProduto={comissaop} setPctProduto={setComissaop} pctServico={comissaos} setPctServico={setComissaos}
                tipo={tipoComissao} setTipo={setTipoComissao} prioridade={prioridadeVendedor} setPrioridade={setPrioridadeVendedor}
                testIDPrefix="func-com-vendedor"
              />
              <ComissaoLinha
                titulo="Executor" pctProduto={comissaopE} setPctProduto={setComissaopE} pctServico={comissaosE} setPctServico={setComissaosE}
                tipo={tipoComissaoE} setTipo={setTipoComissaoE} prioridade={prioridadeExecutor} setPrioridade={setPrioridadeExecutor}
                testIDPrefix="func-com-executor"
              />
              <ComissaoLinha
                titulo="Atendente" pctProduto={comissaopA} setPctProduto={setComissaopA} pctServico={comissaosA} setPctServico={setComissaosA}
                tipo={tipoComissaoA} setTipo={setTipoComissaoA} prioridade={prioridadeAtendente} setPrioridade={setPrioridadeAtendente}
                testIDPrefix="func-com-atendente"
              />

              <View style={styles.switchRow}>
                <Switch value={descontaComissao} onValueChange={setDescontaComissao} testID="func-desconta-comissao" />
                <Text style={styles.switchLabel}>Desconto Comissão</Text>
              </View>

              <View style={styles.gridFormDivider} />
              <Text style={styles.sectionTitle}>Exceções de Comissão</Text>
              {!editing ? <Text style={styles.hint}>Salve o funcionário primeiro para cadastrar exceções.</Text> : (
                <>
                  {comissaoExcecoes.map((ex) => (
                    <View key={ex.cod_comissao_excecao} style={styles.gridRow} testID={`func-excecao-${ex.cod_comissao_excecao}`}>
                      <Text style={styles.gridRowText}>{ex.item} · {ex.descricao} · {tipoExcecaoLabel(ex.tipo)} · {ex.comissao.toFixed(2)}%</Text>
                      <Pressable onPress={() => excluirExcecao(ex)} hitSlop={8}><Ionicons name="trash-outline" size={18} color={colors.error} /></Pressable>
                    </View>
                  ))}
                  <View style={styles.formGrid}>
                    <Field label="Código Produto/Serviço" style={styles.colHalf}>
                      <TextInput value={excecaoItem} onChangeText={setExcecaoItem} style={styles.input} testID="func-excecao-item" />
                    </Field>
                    <Field label="Comissão %" style={styles.colHalf}>
                      <TextInput value={excecaoComissao} onChangeText={setExcecaoComissao} style={styles.input} keyboardType="decimal-pad" testID="func-excecao-comissao" />
                    </Field>
                  </View>
                  <View style={styles.radioRow}>
                    {(["V", "E", "A"] as const).map((t) => (
                      <Pressable key={t} onPress={() => setExcecaoTipo(t)} style={[styles.radioBtn, excecaoTipo === t && styles.radioBtnSel]} testID={`func-excecao-tipo-${t}`}>
                        <View style={[styles.radioCircle, excecaoTipo === t && styles.radioCircleSel]}>{excecaoTipo === t ? <View style={styles.radioDot} /> : null}</View>
                        <Text style={styles.radioLabel}>{tipoExcecaoLabel(t)}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Pressable onPress={gravarExcecao} disabled={excecaoSaving} style={[styles.crudBtn, styles.crudBtnPrimary, excecaoSaving && { opacity: 0.6 }]} testID="func-excecao-gravar">
                    <Text style={styles.crudBtnPrimaryText}>Gravar Exceção</Text>
                  </Pressable>
                </>
              )}
            </View>
          ) : null}

          {tab === "horarios" ? (
            <View style={styles.card} testID="func-tab-content-horarios">
              {DIAS_SEMANA.map((d, i) => {
                const h = horarios[i];
                const set = (patch: Partial<HorarioDia>) => setHorarios((prev) => prev.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
                return (
                  <View key={d.dia} style={styles.horarioDiaBox}>
                    <View style={styles.switchRow}>
                      <Switch value={h.ativo} onValueChange={(v) => set({ ativo: v })} testID={`func-horario-ativo-${d.dia}`} />
                      <Text style={styles.switchLabel}>{d.label}</Text>
                    </View>
                    {h.ativo ? (
                      <View style={styles.formGrid}>
                        <Field label="Disponibilidade de" style={styles.colQuarter}><TextInput value={h.dispIni} onChangeText={(v) => set({ dispIni: formatHora(v) })} style={styles.input} placeholder="HH:MM" maxLength={5} testID={`func-horario-disp-ini-${d.dia}`} /></Field>
                        <Field label="até" style={styles.colQuarter}><TextInput value={h.dispFim} onChangeText={(v) => set({ dispFim: formatHora(v) })} style={styles.input} placeholder="HH:MM" maxLength={5} testID={`func-horario-disp-fim-${d.dia}`} /></Field>
                        <Field label="Intervalo (min)" style={styles.colQuarter}><TextInput value={h.intervalo1} onChangeText={(v) => set({ intervalo1: v.replace(/[^0-9]/g, "") })} style={styles.input} keyboardType="number-pad" testID={`func-horario-intervalo-${d.dia}`} /></Field>
                        <Field label="Encaixe" style={styles.colQuarter}><TextInput value={h.encaixe} onChangeText={(v) => set({ encaixe: v.replace(/[^0-9]/g, "") })} style={styles.input} keyboardType="number-pad" testID={`func-horario-encaixe-${d.dia}`} /></Field>
                        <Field label="Pausa de" style={styles.colQuarter}><TextInput value={h.pausaIni} onChangeText={(v) => set({ pausaIni: formatHora(v) })} style={styles.input} placeholder="HH:MM" maxLength={5} testID={`func-horario-pausa-ini-${d.dia}`} /></Field>
                        <Field label="até" style={styles.colQuarter}><TextInput value={h.pausaFim} onChangeText={(v) => set({ pausaFim: formatHora(v) })} style={styles.input} placeholder="HH:MM" maxLength={5} testID={`func-horario-pausa-fim-${d.dia}`} /></Field>
                      </View>
                    ) : null}
                  </View>
                );
              })}
            </View>
          ) : null}

          {tab === "ausencias" ? (
            <View style={styles.card} testID="func-tab-content-ausencias">
              {!editing ? <Text style={styles.hint}>Salve o funcionário primeiro para cadastrar ausências.</Text> : (
                <>
                  <View style={styles.formGrid}>
                    <Field label="Período de" style={styles.colHalf}><DateField value={ausPeriodoIni} onChange={setAusPeriodoIni} testID="func-aus-periodo-ini" /></Field>
                    <Field label="até" style={styles.colHalf}><DateField value={ausPeriodoFim} onChange={setAusPeriodoFim} testID="func-aus-periodo-fim" /></Field>
                    <Field label="Horário de" style={styles.colQuarter}><TextInput value={ausHoraIni} onChangeText={(v) => setAusHoraIni(formatHora(v))} style={styles.input} placeholder="HH:MM" maxLength={5} testID="func-aus-hora-ini" /></Field>
                    <Field label="até" style={styles.colQuarter}><TextInput value={ausHoraFim} onChangeText={(v) => setAusHoraFim(formatHora(v))} style={styles.input} placeholder="HH:MM" maxLength={5} testID="func-aus-hora-fim" /></Field>
                    <Field label="Intervalo" style={styles.colQuarter}><TextInput value={ausIntervalo} onChangeText={(v) => setAusIntervalo(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="func-aus-intervalo" /></Field>
                  </View>
                  <Field label="Motivo" style={styles.fullWidth}>
                    <TextInput value={ausMotivo} onChangeText={(v) => setAusMotivo(v.toUpperCase())} style={[styles.input, styles.textArea]} multiline testID="func-aus-motivo" />
                  </Field>
                  <Pressable onPress={adicionarAusencia} disabled={ausSaving} style={[styles.crudBtn, styles.crudBtnPrimary, ausSaving && { opacity: 0.6 }]} testID="func-aus-confirmar">
                    <Text style={styles.crudBtnPrimaryText}>Confirmar</Text>
                  </Pressable>

                  <View style={styles.gridFormDivider} />
                  {ausencias.length === 0 ? <Text style={styles.hint}>Nenhuma ausência cadastrada.</Text> : null}
                  {ausencias.map((a) => (
                    <View key={a.codigo_funcionarios_ausencias} style={styles.gridRow} testID={`func-ausencia-${a.codigo_funcionarios_ausencias}`}>
                      <Text style={styles.gridRowText}>
                        {a.data_ini} a {a.data_fim} · {a.hora_ini}-{a.hora_fim} · {a.obs}
                      </Text>
                      <Pressable onPress={() => excluirAusencia(a)} hitSlop={8}><Ionicons name="trash-outline" size={18} color={colors.error} /></Pressable>
                    </View>
                  ))}
                </>
              )}
            </View>
          ) : null}

          {tab === "especialidades" ? (
            <View style={styles.card} testID="func-tab-content-especialidades">
              <View style={styles.sectionTitleRow}>
                <Text style={styles.sectionTitle}>Especialidades do Profissional</Text>
                {canEspecialidades ? (
                  <Pressable onPress={() => setEspecialidadesModalOpen(true)} hitSlop={8} testID="func-especialidades-cadastro-btn">
                    <Ionicons name="settings-outline" size={20} color={colors.brandPrimary} />
                  </Pressable>
                ) : null}
              </View>
              <ChecklistBox options={especialidadeOptions} selected={especialidades} onToggle={(id) => toggleInList(especialidades, setEspecialidades, id)} testIDPrefix="func-especialidade" />
            </View>
          ) : null}

          {editing && canDelete ? (
            <Pressable onPress={handleDelete} style={[styles.crudBtn, styles.crudBtnDanger, { marginTop: spacing.md }]} testID="func-excluir">
              <Text style={styles.crudBtnDangerText}>Excluir Funcionário</Text>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>

      <EspecialidadesCadastroModal
        visible={especialidadesModalOpen}
        onClose={() => setEspecialidadesModalOpen(false)}
        conn={conn}
        auditCtx={auditCtx}
        onChanged={() => conn && loadLookups(conn)}
      />
    </SafeAreaView>
  );
}

function Field({ label, children, style }: { label: string; children: React.ReactNode; style?: object }) {
  return (
    <View style={[{ marginBottom: spacing.md }, style]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

function ChecklistBox({
  options, selected, onToggle, testIDPrefix,
}: { options: SelectOption[]; selected: number[]; onToggle: (id: number) => void; testIDPrefix: string }) {
  if (options.length === 0) {
    return <Text style={styles.hint}>Nenhuma opção disponível.</Text>;
  }
  return (
    <View style={styles.checklistBox}>
      {options.map((o) => {
        const id = Number(o.value);
        const sel = selected.includes(id);
        return (
          <Pressable key={o.value} onPress={() => onToggle(id)} style={styles.checklistRow} testID={`${testIDPrefix}-${o.value}`}>
            <Ionicons name={sel ? "checkbox" : "square-outline"} size={20} color={sel ? colors.brandPrimary : colors.muted} />
            <Text style={styles.checklistLabel}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

type EspecialidadeRow = { codigo: number; descricao: string };

// CRUD embutido de Especialidades (tabela `especialidades`), aberto pelo
// ícone ao lado do título "Especialidades do Profissional" — legado:
// FrmCadEsp, aberto de dentro do próprio FrmManPro. Definido no nível do
// módulo (não dentro de FuncionarioCompletoWeb) — um componente declarado
// dentro do corpo de outro componente ganha identidade nova a cada
// re-render, e o React desmonta/remonta a subárvore inteira a cada tecla
// digitada (perde foco do TextInput). Ver memória de projeto sobre isso.
function EspecialidadesCadastroModal({
  visible, onClose, conn, auditCtx, onChanged,
}: {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  auditCtx: AuditContext;
  onChanged: () => void;
}) {
  const fb = useFeedback();
  const [items, setItems] = useState<EspecialidadeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [editCodigo, setEditCodigo] = useState<number | null>(null);
  const [descricao, setDescricao] = useState("");
  const [saving, setSaving] = useState(false);

  const base = conn ? conn.api.replace(/\/+$/, "") : "";
  const qs = conn ? `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` : "";

  const load = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/especialidades?${qs}`);
      const j = await r.json();
      setItems(j?.success ? (j.items || []).map((i: any) => ({ codigo: i.codigo, descricao: i.descricao })) : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, base, qs]);

  const resetForm = () => {
    setEditCodigo(null);
    setDescricao("");
  };

  useEffect(() => {
    if (visible) {
      load();
      resetForm();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const openEdit = (item: EspecialidadeRow) => {
    setEditCodigo(item.codigo);
    setDescricao(item.descricao);
  };

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) {
      fb.showWarning("Preencha a Descrição da Especialidade.");
      return;
    }
    setSaving(true);
    try {
      const r = await fetch(`${base}/api/tabelas/especialidades`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCodigo, descricao: descricao.trim() }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Registro Gravado.");
        resetForm();
        load();
        onChanged();
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: EspecialidadeRow) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão de "${item.descricao}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const r = await fetch(`${base}/api/tabelas/especialidades/${item.codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) {
              fb.showSuccess(j.message || "Registro Excluído.");
              if (editCodigo === item.codigo) resetForm();
              load();
              onChanged();
            } else {
              fb.showError(j?.message || "Falha ao excluir.");
            }
          } catch (e) {
            fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
          }
        },
      },
    ]);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.especModalBg} onPress={onClose}>
        <Pressable style={styles.especModalCard} onPress={(e) => e.stopPropagation()}>
          <Text style={styles.sectionTitle}>Cadastro de Especialidades</Text>

          <Field label="Descrição da Especialidade">
            <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={50} testID="especialidade-descricao" />
          </Field>

          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={resetForm} style={[styles.crudBtn, { flex: 1 }]} testID="especialidade-novo">
              <Text style={styles.crudBtnText}>Novo</Text>
            </Pressable>
            <Pressable onPress={save} disabled={saving} style={[styles.crudBtn, styles.crudBtnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} testID="especialidade-gravar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.crudBtnPrimaryText}>Gravar</Text>}
            </Pressable>
            <Pressable onPress={onClose} style={[styles.crudBtn, { flex: 1 }]} testID="especialidade-sair">
              <Text style={styles.crudBtnText}>Sair</Text>
            </Pressable>
          </View>

          <View style={styles.gridFormDivider} />

          <ScrollView style={styles.especModalList}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
            {!loading && items.length === 0 ? <Text style={styles.hint}>Nenhuma especialidade cadastrada.</Text> : null}
            {items.map((it) => (
              <Pressable key={it.codigo} onPress={() => openEdit(it)} style={styles.gridRow} testID={`especialidade-row-${it.codigo}`}>
                <Text style={styles.gridRowText}>{it.codigo} — {it.descricao}</Text>
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`especialidade-del-${it.codigo}`}>
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </Pressable>
              </Pressable>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function ComissaoLinha({
  titulo, pctProduto, setPctProduto, pctServico, setPctServico, tipo, setTipo, prioridade, setPrioridade, testIDPrefix,
}: {
  titulo: string; pctProduto: string; setPctProduto: (v: string) => void; pctServico: string; setPctServico: (v: string) => void;
  tipo: string | null; setTipo: (v: string | null) => void; prioridade: boolean; setPrioridade: (v: boolean) => void; testIDPrefix: string;
}) {
  return (
    <View style={styles.comissaoLinha}>
      <Text style={styles.comissaoTitulo}>{titulo}</Text>
      <View style={styles.formGrid}>
        <Field label="Produto %" style={styles.colQuarter}><TextInput value={pctProduto} onChangeText={setPctProduto} style={styles.input} keyboardType="decimal-pad" testID={`${testIDPrefix}-produto`} /></Field>
        <Field label="Serviços %" style={styles.colQuarter}><TextInput value={pctServico} onChangeText={setPctServico} style={styles.input} keyboardType="decimal-pad" testID={`${testIDPrefix}-servico`} /></Field>
        <Field label="Tipo de Comissão" style={styles.colHalf}><SelectField value={tipo} onChange={(v) => setTipo(v as string)} options={TIPO_COMISSAO_OPTS} testID={`${testIDPrefix}-tipo`} modalTitle="Tipo de Comissão" compactWeb /></Field>
      </View>
      <View style={styles.switchRow}>
        <Switch value={prioridade} onValueChange={setPrioridade} testID={`${testIDPrefix}-prioridade`} />
        <Text style={styles.switchLabel}>Prioridade</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)",
    minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  tabBar: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg, flexWrap: "wrap" },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 10,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  formGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.md },
  colHalf: { width: "49%" },
  colQuarter: { width: "24%" },
  fullWidth: { width: "100%" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  inputDisabled: { backgroundColor: colors.surfaceTertiary, color: colors.muted },
  textArea: { minHeight: 70, textAlignVertical: "top" },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6, marginTop: 4 },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  checklistBox: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary,
    padding: spacing.sm, maxHeight: 160,
  },
  checklistRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 6 },
  checklistLabel: { fontSize: 13, color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted, fontStyle: "italic", marginVertical: spacing.sm },
  sectionTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface, marginBottom: spacing.sm, textTransform: "uppercase", letterSpacing: 0.5 },
  sectionTitleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  gridFormDivider: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: spacing.md, marginBottom: spacing.md },
  gridRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 10, paddingHorizontal: spacing.sm,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: 6,
  },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  crudBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", marginTop: spacing.sm },
  crudBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  crudBtnDanger: { backgroundColor: colors.surface, borderColor: colors.error },
  crudBtnDangerText: { fontSize: 13, fontWeight: "600", color: colors.error },
  especModalBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.xl,
  },
  especModalCard: {
    width: "100%", maxWidth: 480, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg,
  },
  especModalList: { maxHeight: 280 },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: spacing.md, marginTop: spacing.sm },
  radioBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  horarioDiaBox: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: spacing.sm, marginBottom: spacing.sm },
  comissaoLinha: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: spacing.sm, marginBottom: spacing.sm },
  comissaoTitulo: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.xs, textTransform: "uppercase" },
});
