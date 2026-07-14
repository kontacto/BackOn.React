import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_SERVICO } from "@/src/components/GestorDocumentosSection";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import NiveisModal from "@/src/components/NiveisModal";
import PrevisaoProdutosModal from "@/src/components/PrevisaoProdutosModal";

type Conn = Connection;
type NivelFlat = { codigo: string; descricao: string; niveis: string[] };
type ServicoItem = { codigo: string; descricao: string; situacao: string; valor_hora: number };
type ServicoDetalhe = {
  codigo: string; descricao: string; descricao_nf: string; codigo_especialidade: number | null;
  tipo: number; situacao: string; valor_hora: number; custo_hora: number; preco_variado: boolean;
  prazo_garantia: number; tipo_garantia: number;
  nivel1: string; nivel2: string; nivel3: string; nivel4: string; nivel5: string;
  cod_lista_servico: string; cod_servico_municipio: string; cod_icms: string; indop_nfse: string;
  codigo_mercosul: string; classificacao_fiscal: string; construcao_civil: boolean;
  tributacao_pis: string | null; perc_valor_pis: number; tributacao_cofins: string | null; perc_valor_cofins: number;
  aceita_desconto: boolean; desc_g: number; desc_s: number; desc_v: number;
  paga_comissao: boolean; comissao: number; comissao_e: number; comissao_a: number;
  valor_comissao: number; valor_comissao_e: number; valor_comissao_a: number;
  perc_desc_base_comissao: number; perc_desc_base_comissao_e: number; perc_desc_base_comissao_a: number;
};

const TIPO_GARANTIA_OPTS: SelectOption[] = [
  { value: 0, label: "Nenhum" },
  { value: 1, label: "Ano(s)" },
  { value: 2, label: "Dia(s)" },
  { value: 3, label: "Hora(s)" },
  { value: 4, label: "Mês(es)" },
  { value: 5, label: "Km" },
];

const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);
const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);

type TabKey = "principal" | "fiscal" | "descontos" | "anexos";
const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "principal", label: "Principal", icon: "construct-outline" },
  { key: "fiscal", label: "Configurações Fiscais", icon: "receipt-outline" },
  { key: "descontos", label: "Descontos, Comissões e Outros", icon: "pricetag-outline" },
  { key: "anexos", label: "Anexos", icon: "attach-outline" },
];

// Cadastro > Serviços (tabela `servicos`). Legado: FrmManSer2.frm
// ("Manutenção de Serviços"). Fase 1 (CRUD principal) — ver memória de
// projeto "Servicos Manutencao" para o desenho completo. Classificação
// Mercadológica (níveis) é somente leitura aqui — mesma árvore `niveis`
// compartilhada com Produtos, seleção via NiveisModal (sem CRUD de
// árvore nesta tela). Ainda fora de escopo: Previsão de Produtos, Preço
// por Quantidade, Layouts, Exceções de Comissão — sub-telas do legado
// ainda não migradas.
//
// Layout do formulário segue o padrão de cliente-completo.tsx (header com
// Gravar no topo direito, abas com ícone, conteúdo em cards full-width) —
// ver CLAUDE.md > "Padrão de Tela CRUD (Form em Abas)".
export default function ServicosScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Serviços está disponível apenas no web."
        testID="servicos-web-only"
      />
    );
  }

  if (!moduleOn("servicos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Serviços está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="servicos-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<ServicoItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [tipoServicoOptions, setTipoServicoOptions] = useState<SelectOption[]>([]);
  const [especialidadeOptions, setEspecialidadeOptions] = useState<SelectOption[]>([]);
  const [cstPisOptions, setCstPisOptions] = useState<SelectOption[]>([]);
  const [cstCofinsOptions, setCstCofinsOptions] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [tab, setTab] = useState<TabKey>("principal");
  const [editingCodigo, setEditingCodigo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [descricaoNf, setDescricaoNf] = useState("");
  const [especialidade, setEspecialidade] = useState<number | null>(null);
  const [tipoServico, setTipoServico] = useState<number | null>(0);
  const [situacao, setSituacao] = useState("A");
  const [valorHora, setValorHora] = useState("");
  const [custoHora, setCustoHora] = useState("");
  const [precoVariado, setPrecoVariado] = useState(false);
  const [prazoGarantia, setPrazoGarantia] = useState("");
  const [tipoGarantia, setTipoGarantia] = useState<number | null>(0);

  const [codListaServico, setCodListaServico] = useState("");
  const [codServicoMunicipio, setCodServicoMunicipio] = useState("");
  const [codIcms, setCodIcms] = useState("");
  const [indopNfse, setIndopNfse] = useState("");
  const [codigoMercosul, setCodigoMercosul] = useState("");
  const [classificacaoFiscal, setClassificacaoFiscal] = useState("");
  const [construcaoCivil, setConstrucaoCivil] = useState(false);
  const [tributacaoPis, setTributacaoPis] = useState<string | null>(null);
  const [percValorPis, setPercValorPis] = useState("");
  const [tributacaoCofins, setTributacaoCofins] = useState<string | null>(null);
  const [percValorCofins, setPercValorCofins] = useState("");

  const [aceitaDesconto, setAceitaDesconto] = useState(false);
  const [descG, setDescG] = useState("");
  const [descS, setDescS] = useState("");
  const [descV, setDescV] = useState("");
  const [pagaComissao, setPagaComissao] = useState(false);
  const [comissao, setComissao] = useState("");
  const [comissaoE, setComissaoE] = useState("");
  const [comissaoA, setComissaoA] = useState("");
  const [valorComissao, setValorComissao] = useState("");
  const [valorComissaoE, setValorComissaoE] = useState("");
  const [valorComissaoA, setValorComissaoA] = useState("");
  const [percDescBaseComissao, setPercDescBaseComissao] = useState("");
  const [percDescBaseComissaoE, setPercDescBaseComissaoE] = useState("");
  const [percDescBaseComissaoA, setPercDescBaseComissaoA] = useState("");

  const [nivelSegments, setNivelSegments] = useState<string[]>(["", "", "", "", ""]);
  const [nivelLabel, setNivelLabel] = useState("");
  const [nivelModalOpen, setNivelModalOpen] = useState(false);
  const [nivelList, setNivelList] = useState<NivelFlat[]>([]);

  const [prevProdutosOpen, setPrevProdutosOpen] = useState(false);

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/servicos?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rTipo, rEsp, rPis, rCofins] = await Promise.all([
        fetch(`${base}/api/tabelas/tipo-servico?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/especialidades?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/cst-pis?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/cst-cofins?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rTipo?.success) setTipoServicoOptions(rTipo.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rEsp?.success) setEspecialidadeOptions(rEsp.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rPis?.success) setCstPisOptions(rPis.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} — ${i.descricao}` })));
      if (rCofins?.success) setCstCofinsOptions(rCofins.items.map((i: any) => ({ value: i.codigo, label: `${i.codigo} — ${i.descricao}` })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  const loadNiveis = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/relatorios/margem-lucro/niveis?${qs}`);
      const j = await r.json();
      if (j?.success) setNivelList(j.niveis || []);
    } catch {
      // silencioso — seletor de nível fica sem opção de resolver o label atual
    }
  }, []);

  const findNivelLabel = useCallback((segments: string[]): string => {
    const codigo = segments.filter((p) => p && p.trim()).join("");
    if (!codigo) return "";
    const found = nivelList.find((n) => n.codigo === codigo);
    return found ? `${found.codigo} · ${found.descricao}` : codigo;
  }, [nivelList]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c);
      loadLookups(c);
      loadNiveis(c);
    })();
  }, [router, load, loadLookups, loadNiveis]);

  const filtered = items.filter((i) =>
    !search.trim() ||
    i.codigo.toLowerCase().includes(search.toLowerCase()) ||
    i.descricao.toLowerCase().includes(search.toLowerCase())
  );

  const resetForm = () => {
    setCodigo(""); setDescricao(""); setDescricaoNf(""); setEspecialidade(null); setTipoServico(0);
    setSituacao("A"); setValorHora(""); setCustoHora(""); setPrecoVariado(false);
    setPrazoGarantia(""); setTipoGarantia(0);
    setCodListaServico(""); setCodServicoMunicipio(""); setCodIcms(""); setIndopNfse(""); setCodigoMercosul("");
    setClassificacaoFiscal(""); setConstrucaoCivil(false);
    setTributacaoPis(null); setPercValorPis(""); setTributacaoCofins(null); setPercValorCofins("");
    setAceitaDesconto(false); setDescG(""); setDescS(""); setDescV("");
    setPagaComissao(false); setComissao(""); setComissaoE(""); setComissaoA("");
    setValorComissao(""); setValorComissaoE(""); setValorComissaoA("");
    setPercDescBaseComissao(""); setPercDescBaseComissaoE(""); setPercDescBaseComissaoA("");
    setNivelSegments(["", "", "", "", ""]); setNivelLabel("");
  };

  const openNew = () => {
    setEditingCodigo(null);
    resetForm();
    setTab("principal");
    setFormOpen(true);
  };

  const openEdit = async (item: ServicoItem) => {
    if (!conn) return;
    setEditingCodigo(item.codigo);
    setTab("principal");
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/servicos/${item.codigo}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d: ServicoDetalhe = j.item;
      setCodigo(d.codigo); setDescricao(d.descricao); setDescricaoNf(d.descricao_nf || "");
      setEspecialidade(d.codigo_especialidade); setTipoServico(d.tipo); setSituacao(d.situacao || "A");
      setValorHora(String(d.valor_hora ?? "")); setCustoHora(String(d.custo_hora ?? ""));
      setPrecoVariado(d.preco_variado); setPrazoGarantia(String(d.prazo_garantia ?? "")); setTipoGarantia(d.tipo_garantia);
      setCodListaServico(d.cod_lista_servico); setCodServicoMunicipio(d.cod_servico_municipio);
      setCodIcms(d.cod_icms); setIndopNfse(d.indop_nfse || ""); setCodigoMercosul(d.codigo_mercosul); setClassificacaoFiscal(d.classificacao_fiscal);
      setConstrucaoCivil(d.construcao_civil);
      setTributacaoPis(d.tributacao_pis); setPercValorPis(String(d.perc_valor_pis ?? ""));
      setTributacaoCofins(d.tributacao_cofins); setPercValorCofins(String(d.perc_valor_cofins ?? ""));
      setAceitaDesconto(d.aceita_desconto); setDescG(String(d.desc_g ?? "")); setDescS(String(d.desc_s ?? "")); setDescV(String(d.desc_v ?? ""));
      setPagaComissao(d.paga_comissao); setComissao(String(d.comissao ?? "")); setComissaoE(String(d.comissao_e ?? "")); setComissaoA(String(d.comissao_a ?? ""));
      setValorComissao(String(d.valor_comissao ?? "")); setValorComissaoE(String(d.valor_comissao_e ?? "")); setValorComissaoA(String(d.valor_comissao_a ?? ""));
      setPercDescBaseComissao(String(d.perc_desc_base_comissao ?? "")); setPercDescBaseComissaoE(String(d.perc_desc_base_comissao_e ?? "")); setPercDescBaseComissaoA(String(d.perc_desc_base_comissao_a ?? ""));
      const segs = [d.nivel1 || "", d.nivel2 || "", d.nivel3 || "", d.nivel4 || "", d.nivel5 || ""];
      setNivelSegments(segs);
      setNivelLabel(findNivelLabel(segs));
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const save = async () => {
    if (!conn) return;
    if (!codigo.trim()) { fb.showWarning("Defina o Código do Serviço!"); setTab("principal"); return; }
    if (!descricao.trim()) { fb.showWarning("Defina a Descrição!"); setTab("principal"); return; }
    if (!valorHora.trim()) { fb.showWarning("Defina o Preço/Hora!"); setTab("principal"); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/servicos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: codigo.trim().toUpperCase(),
          dados: {
            descricao: descricao.trim(), descricao_nf: descricaoNf.trim(),
            codigo_especialidade: especialidade, tipo: tipoServico ?? 0, situacao: situacao.trim().toUpperCase() || "A",
            valor_hora: num(valorHora), custo_hora: num(custoHora), preco_variado: precoVariado,
            prazo_garantia: int_(prazoGarantia), tipo_garantia: tipoGarantia ?? 0,
            nivel1: nivelSegments[0], nivel2: nivelSegments[1], nivel3: nivelSegments[2],
            nivel4: nivelSegments[3], nivel5: nivelSegments[4],
            cod_lista_servico: codListaServico.trim(), cod_servico_municipio: codServicoMunicipio.trim(),
            cod_icms: codIcms.trim(), indop_nfse: indopNfse.trim(), codigo_mercosul: codigoMercosul.trim(), classificacao_fiscal: classificacaoFiscal.trim(),
            construcao_civil: construcaoCivil,
            tributacao_pis: tributacaoPis, perc_valor_pis: num(percValorPis),
            tributacao_cofins: tributacaoCofins, perc_valor_cofins: num(percValorCofins),
            aceita_desconto: aceitaDesconto, desc_g: num(descG), desc_s: num(descS), desc_v: num(descV),
            paga_comissao: pagaComissao, comissao: num(comissao), comissao_e: num(comissaoE), comissao_a: num(comissaoA),
            valor_comissao: num(valorComissao), valor_comissao_e: num(valorComissaoE), valor_comissao_a: num(valorComissaoA),
            perc_desc_base_comissao: num(percDescBaseComissao), perc_desc_base_comissao_e: num(percDescBaseComissaoE),
            perc_desc_base_comissao_a: num(percDescBaseComissaoA),
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Serviço gravado.");
        setEditingCodigo(j.codigo);
        setCodigo(j.codigo);
        load(conn);
      } else {
        fb.showError(j?.message || (Array.isArray(j?.detail) ? j.detail.map((d: any) => d.msg).join("; ") : "Falha ao gravar."));
      }
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = (item: ServicoItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão do serviço "${item.codigo}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/servicos/${item.codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const handleNivelPick = (codigoNivel: string, label: string) => {
    setNivelModalOpen(false);
    if (!codigoNivel) {
      setNivelSegments(["", "", "", "", ""]);
      setNivelLabel("");
      return;
    }
    const found = nivelList.find((n) => n.codigo === codigoNivel);
    if (found) {
      setNivelSegments(found.niveis);
      setNivelLabel(`${found.codigo} · ${found.descricao}`);
    } else {
      setNivelSegments(["", "", "", "", ""]);
      setNivelLabel(label);
    }
  };

  const canSave = can("SERVICO.GRAVAR") || isMaster;
  const canDel = can("SERVICO.EXCLUIR") || isMaster;

  // ============================================================
  // Formulário (tela cheia) — padrão cliente-completo.tsx
  // ============================================================
  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="servicos-form-screen">
        <View style={styles.header}>
          <Pressable
            onPress={() => setFormOpen(false)}
            style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]}
            hitSlop={12}
            testID="servicos-form-back-button"
          >
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
          <Text style={styles.headerTitle} numberOfLines={1}>
            {editingCodigo ? `Serviço ${editingCodigo}` : "Novo Serviço"}
          </Text>
          {canSave ? (
            <Pressable
              onPress={save}
              disabled={saving}
              style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]}
              hitSlop={8}
              testID="servicos-salvar"
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} size="small" />
              ) : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : (
            <View style={{ width: 40 }} />
          )}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            <View style={styles.tabBar}>
              {TABS.filter((t) => t.key !== "anexos" || !!editingCodigo).map((t) => {
                const sel = tab === t.key;
                return (
                  <Pressable
                    key={t.key}
                    onPress={() => setTab(t.key)}
                    style={({ pressed }) => [styles.tabBtn, sel && styles.tabBtnSel, pressed && { opacity: 0.85 }]}
                    testID={`servicos-tab-${t.key}`}
                  >
                    <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                    <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            {tab === "principal" ? (
              <View style={styles.card} testID="servicos-tab-content-principal">
                <View style={styles.rowFields}>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Código *</Text>
                    <TextInput value={codigo} onChangeText={(v) => setCodigo(v.toUpperCase())} style={styles.input} maxLength={8} autoCapitalize="characters" editable={!editingCodigo} testID="servicos-codigo" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Descrição *</Text>
                    <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={50} testID="servicos-descricao" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Situação</Text>
                    <TextInput value={situacao} onChangeText={(v) => setSituacao(v.toUpperCase())} style={styles.input} maxLength={2} testID="servicos-situacao" />
                  </View>
                </View>

                <Text style={styles.label}>Descrição Nota Fiscal</Text>
                <TextInput value={descricaoNf} onChangeText={setDescricaoNf} style={[styles.input, { minHeight: 60 }]} multiline testID="servicos-descricao-nf" />

                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Especialidade do Serviço</Text>
                    <SelectField value={especialidade} onChange={(v) => setEspecialidade(v as number)} options={especialidadeOptions} allowClear testID="servicos-especialidade" modalTitle="Especialidade" compactWeb />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Tipo</Text>
                    <SelectField value={tipoServico} onChange={(v) => setTipoServico(v as number)} options={tipoServicoOptions} testID="servicos-tipo" modalTitle="Tipo" compactWeb />
                  </View>
                </View>

                <Text style={styles.sectionTitle}>Preço e Custo</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Preço/Hora *</Text>
                    <TextInput value={valorHora} onChangeText={setValorHora} style={styles.input} keyboardType="decimal-pad" testID="servicos-valor-hora" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Custo/Hora</Text>
                    <TextInput value={custoHora} onChangeText={setCustoHora} style={styles.input} keyboardType="decimal-pad" testID="servicos-custo-hora" />
                  </View>
                </View>
                <View style={styles.checkRow}>
                  <Switch value={precoVariado} onValueChange={setPrecoVariado} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="servicos-preco-variado" />
                  <Text style={styles.checkLabel}>Preço Variado</Text>
                </View>

                <Text style={styles.sectionTitle}>Garantia</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Prazo Garantia</Text>
                    <TextInput value={prazoGarantia} onChangeText={(v) => setPrazoGarantia(v.replace(/[^0-9]/g, ""))} style={styles.input} keyboardType="number-pad" testID="servicos-prazo-garantia" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Tipo Garantia</Text>
                    <SelectField value={tipoGarantia} onChange={(v) => setTipoGarantia(v as number)} options={TIPO_GARANTIA_OPTS} testID="servicos-tipo-garantia" modalTitle="Tipo Garantia" compactWeb />
                  </View>
                </View>

                <Text style={styles.sectionTitle}>Classificação Mercadológica</Text>
                <Pressable onPress={() => setNivelModalOpen(true)} style={styles.nivelBox} testID="servicos-nivel-selecionar">
                  <Text style={nivelLabel ? styles.nivelValue : styles.nivelPlaceholder}>
                    {nivelLabel || "Nenhum nível selecionado"}
                  </Text>
                  <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>

                {editingCodigo && can("SERVICO.PREV_PRODUTOS") ? (
                  <>
                    <Text style={styles.sectionTitle}>Composição</Text>
                    <Pressable onPress={() => setPrevProdutosOpen(true)} style={styles.nivelBox} testID="servicos-previsao-produtos-abrir">
                      <Text style={styles.nivelValue}>Previsão de Produtos</Text>
                      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                    </Pressable>
                  </>
                ) : null}

                <Text style={styles.sectionHint}>
                  Preço por Quantidade, Layouts e Exceções de Comissão ainda não estão disponíveis nesta versão
                  da tela.
                </Text>
              </View>
            ) : null}

            {tab === "fiscal" ? (
              <View style={styles.card} testID="servicos-tab-content-fiscal">
                <Text style={styles.sectionTitle}>Códigos / Classificações</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Código de Tributação Nacional</Text>
                    <TextInput value={codListaServico} onChangeText={setCodListaServico} style={styles.input} maxLength={15} testID="servicos-cod-lista-servico" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Código Complementar Municipal</Text>
                    <TextInput value={codServicoMunicipio} onChangeText={setCodServicoMunicipio} style={styles.input} maxLength={15} testID="servicos-cod-servico-municipio" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Código Mercosul</Text>
                    <TextInput value={codigoMercosul} onChangeText={setCodigoMercosul} style={styles.input} maxLength={8} testID="servicos-codigo-mercosul" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Classificação Fiscal</Text>
                    <TextInput value={classificacaoFiscal} onChangeText={setClassificacaoFiscal} style={styles.input} maxLength={8} testID="servicos-classificacao-fiscal" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Código ICMS</Text>
                    <TextInput value={codIcms} onChangeText={setCodIcms} style={styles.input} maxLength={3} testID="servicos-cod-icms" />
                  </View>
                  <View style={styles.colFlex}>
                    <Text style={styles.label}>Indicador Operação</Text>
                    <TextInput value={indopNfse} onChangeText={setIndopNfse} style={styles.input} maxLength={10} testID="servicos-indop-nfse" />
                  </View>
                </View>
                <View style={styles.checkRow}>
                  <Switch value={construcaoCivil} onValueChange={setConstrucaoCivil} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="servicos-construcao-civil" />
                  <Text style={styles.checkLabel}>NFSe Construção Civil</Text>
                </View>

                <Text style={styles.sectionTitle}>Impostos</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>PIS — CST</Text>
                    <SelectField value={tributacaoPis} onChange={(v) => setTributacaoPis(v as string)} options={cstPisOptions} allowClear testID="servicos-pis-cst" modalTitle="CST PIS" compactWeb />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>PIS — Alíquota</Text>
                    <TextInput value={percValorPis} onChangeText={setPercValorPis} style={styles.input} keyboardType="decimal-pad" testID="servicos-pis-aliquota" />
                  </View>
                </View>
                <View style={styles.rowFields}>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Cofins — CST</Text>
                    <SelectField value={tributacaoCofins} onChange={(v) => setTributacaoCofins(v as string)} options={cstCofinsOptions} allowClear testID="servicos-cofins-cst" modalTitle="CST Cofins" compactWeb />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.label}>Cofins — Alíquota</Text>
                    <TextInput value={percValorCofins} onChangeText={setPercValorCofins} style={styles.input} keyboardType="decimal-pad" testID="servicos-cofins-aliquota" />
                  </View>
                </View>
              </View>
            ) : null}

            {tab === "descontos" ? (
              <View style={styles.card} testID="servicos-tab-content-descontos">
                <View style={styles.checkRow}>
                  <Switch value={aceitaDesconto} onValueChange={setAceitaDesconto} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="servicos-aceita-desconto" />
                  <Text style={styles.checkLabel}>Aceita Desconto</Text>
                </View>
                {aceitaDesconto ? (
                  <View style={styles.rowFields}>
                    <View style={styles.colThird}>
                      <Text style={styles.label}>Gerente</Text>
                      <TextInput value={descG} onChangeText={setDescG} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-g" />
                    </View>
                    <View style={styles.colThird}>
                      <Text style={styles.label}>Supervisor</Text>
                      <TextInput value={descS} onChangeText={setDescS} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-s" />
                    </View>
                    <View style={styles.colThird}>
                      <Text style={styles.label}>Vendedor</Text>
                      <TextInput value={descV} onChangeText={setDescV} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-v" />
                    </View>
                  </View>
                ) : null}

                <View style={styles.checkRow}>
                  <Switch value={pagaComissao} onValueChange={setPagaComissao} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="servicos-paga-comissao" />
                  <Text style={styles.checkLabel}>Paga Comissão</Text>
                </View>
                {pagaComissao ? (
                  <>
                    <Text style={styles.sectionTitle}>Comissão por Percentual</Text>
                    <View style={styles.rowFields}>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Vendedor</Text>
                        <TextInput value={comissao} onChangeText={setComissao} style={styles.input} keyboardType="decimal-pad" testID="servicos-comissao-v" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Executor</Text>
                        <TextInput value={comissaoE} onChangeText={setComissaoE} style={styles.input} keyboardType="decimal-pad" testID="servicos-comissao-e" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Atendente</Text>
                        <TextInput value={comissaoA} onChangeText={setComissaoA} style={styles.input} keyboardType="decimal-pad" testID="servicos-comissao-a" />
                      </View>
                    </View>

                    <Text style={styles.sectionTitle}>Comissão por Valor</Text>
                    <View style={styles.rowFields}>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Vendedor</Text>
                        <TextInput value={valorComissao} onChangeText={setValorComissao} style={styles.input} keyboardType="decimal-pad" testID="servicos-valor-comissao-v" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Executor</Text>
                        <TextInput value={valorComissaoE} onChangeText={setValorComissaoE} style={styles.input} keyboardType="decimal-pad" testID="servicos-valor-comissao-e" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Atendente</Text>
                        <TextInput value={valorComissaoA} onChangeText={setValorComissaoA} style={styles.input} keyboardType="decimal-pad" testID="servicos-valor-comissao-a" />
                      </View>
                    </View>

                    <Text style={styles.sectionTitle}>Desconto sobre Base de Comissão</Text>
                    <View style={styles.rowFields}>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Vendedor</Text>
                        <TextInput value={percDescBaseComissao} onChangeText={setPercDescBaseComissao} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-base-v" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Executor</Text>
                        <TextInput value={percDescBaseComissaoE} onChangeText={setPercDescBaseComissaoE} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-base-e" />
                      </View>
                      <View style={styles.colThird}>
                        <Text style={styles.label}>Atendente</Text>
                        <TextInput value={percDescBaseComissaoA} onChangeText={setPercDescBaseComissaoA} style={styles.input} keyboardType="decimal-pad" testID="servicos-desc-base-a" />
                      </View>
                    </View>
                  </>
                ) : null}

                <Text style={styles.sectionHint}>Exceções de Comissão por funcionário ainda não estão disponíveis nesta versão da tela.</Text>
              </View>
            ) : null}

            {tab === "anexos" && conn && editingCodigo ? (
              <>
                <View style={styles.sectionHeader} testID="servicos-tab-content-anexos">
                  <Text style={styles.sectionHeaderTitle}>Documentos Anexados</Text>
                </View>
                <View style={styles.card}>
                  <GestorDocumentosSection
                    api={conn.api}
                    servidor={conn.servidor}
                    banco={conn.banco}
                    codGrupo={GESTOR_DOC_GRUPO_SERVICO}
                    codigoEntidade={editingCodigo}
                  />
                </View>
              </>
            ) : null}
          </View>
        </ScrollView>

        <NiveisModal visible={nivelModalOpen} conn={conn} onClose={() => setNivelModalOpen(false)} onPick={handleNivelPick} />

        <PrevisaoProdutosModal
          visible={prevProdutosOpen}
          conn={conn}
          principal={editingCodigo || ""}
          principalLabel={editingCodigo ? `${editingCodigo} · ${descricao}` : ""}
          onClose={() => setPrevProdutosOpen(false)}
          canEdit={canSave}
        />
      </SafeAreaView>
    );
  }

  // ============================================================
  // Lista
  // ============================================================
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="servicos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Serviços</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.listShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por código ou descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="servicos-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && filtered.length === 0 ? <Text style={styles.empty}>Nenhum serviço cadastrado.</Text> : null}
          {filtered.map((s) => (
            <View key={s.codigo} style={styles.row} testID={`servicos-${s.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(s)}>
                <Text style={styles.rowTitle}>{s.codigo} · {s.descricao || "—"}</Text>
                <Text style={styles.rowSub}>
                  Preço/Hora: {s.valor_hora.toFixed(2)}{s.situacao && s.situacao !== "A" ? ` · ${s.situacao}` : ""}
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(s)} hitSlop={8} testID={`servicos-del-${s.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="servicos-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.3)",
    minWidth: 90,
    justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  // ---- Lista ----
  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  // ---- Formulário ----
  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  tabBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  tabBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: spacing.sm, width: "100%", maxWidth: 1120, alignSelf: "center",
  },
  sectionHeaderTitle: { fontSize: 14, fontWeight: "500", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5 },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs },
  sectionHint: { fontSize: 11, color: colors.muted, marginTop: spacing.md, fontStyle: "italic" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  colHalf: { flex: 1 },
  colThird: { flex: 1 },
  colFlex: { flex: 1, minWidth: 0 },
  colNarrow: { width: 140 },
  colTiny: { width: 90 },
  checkRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  checkLabel: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  nivelBox: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 12,
  },
  nivelValue: { fontSize: 14, color: colors.onSurface, fontWeight: "500", flex: 1 },
  nivelPlaceholder: { fontSize: 14, color: colors.muted, flex: 1 },
});
