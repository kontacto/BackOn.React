// Financeiro > Contas a Receber — gerencia o que já foi lançado em
// `Duplicata_Receber`/`Duplicata_Rec_Venc` (via Transferência p/Contas
// Pagar/Receber, Contratos/Faturar, ou lançamento manual avulso aqui
// mesmo). Fonte VB6 rastreada: `Geral/FRMCONNFREC.frm` (consulta) +
// `Geral/frmTraNFRec.frm` (CRUD/avulso) + `Revenda/FrmManDur.frm`
// (manutenção de duplicata/parcelas) — ver
// backend/services/contas_receber_service.py pro rastreio completo.
//
// Escopo desta 1ª rodada (AskUserQuestion, 2026-08-28): lançamento avulso
// + baixa manual (funcionalidade NOVA, sem precedente no legado — só
// existe baixa via retorno CNAB lá) + exclusão com guarda. Boleto avulso/
// Centro de Resultados/Emitir Fatura ficam de fora, aguardando o usuário
// confirmar escopo com Leandro.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import { styles as ps } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR, parseNum, todayISO } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type Duplicata = {
  codigo: number; cliente: number; cliente_nome: string; duplicata: number; desmembramento: string | null;
  dt_emissao: string | null; valor: number; situacao: string; num_parcelas: number; parcelas_pagas: number;
  proximo_vencimento: string | null; valor_em_aberto: number; vencido: boolean;
};

type Parcela = {
  codigo: number; desmembramento: number; dt_vencimento: string | null; valor: number; situacao: string;
  data_pag: string | null; valor_pag: number | null; desconto_pag: number | null; juros_pag: number | null;
  conta: number | null; forma_pag: string | null; observacao: string | null;
};

type Detalhe = { header: Duplicata; parcelas: Parcela[]; notas: { codigo: number; nota_fiscal: number; serie: string }[] };

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que esta tela faz", texto: "Lista as duplicatas a receber já lançadas (vindas de Nota Fiscal, Comanda, Contrato faturado, ou digitadas aqui mesmo) e deixa acompanhar/baixar as parcelas.", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Lançamento avulso", texto: "Use quando você tem um valor a receber que não veio de Nota Fiscal nem Comanda — digite cliente, valor e vencimento(s) direto.", icon: { lib: "ion", name: "add-circle-outline" } },
  { titulo: "Baixa manual", texto: "Marca uma parcela como paga quando o cliente pagou por dinheiro, PIX ou transferência direta (sem passar por boleto/banco). Uma vez baixada, a parcela não pode mais ser editada.", icon: { lib: "ion", name: "checkmark-done-outline" } },
  { titulo: "Vencido", texto: "Parcela em aberto cuja data de vencimento já passou — aparece em destaque vermelho.", icon: { lib: "ion", name: "alert-circle-outline" } },
  { titulo: "Excluir", texto: "Só é possível excluir uma duplicata se NENHUMA parcela dela já tiver sido paga.", icon: { lib: "ion", name: "trash-outline" } },
];

const SITUACOES: { key: string; label: string }[] = [
  { key: "", label: "Todas" }, { key: "A", label: "Aberto" }, { key: "V", label: "Vencido" }, { key: "PG", label: "Pago" },
];

export default function ContasReceberScreen() {
  const router = useRouter();
  const { can, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [filtrosExpandido, setFiltrosExpandido] = useState(true);
  const [busca, setBusca] = useState("");
  const [situacao, setSituacao] = useState("");
  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [usarPeriodo, setUsarPeriodo] = useState(false);
  const [items, setItems] = useState<Duplicata[]>([]);

  const [tiposMov, setTiposMov] = useState<SelectOption[]>([]);

  // ---- Lançamento avulso ----
  const [avulsoOpen, setAvulsoOpen] = useState(false);
  const [salvandoAvulso, setSalvandoAvulso] = useState(false);
  const [avClienteCod, setAvClienteCod] = useState<number | null>(null);
  const [avClienteNome, setAvClienteNome] = useState("");
  const [avClienteSearchOpen, setAvClienteSearchOpen] = useState(false);
  const [avClienteTerm, setAvClienteTerm] = useState("");
  const [avClienteResults, setAvClienteResults] = useState<ClienteRow[]>([]);
  const [avClienteLoading, setAvClienteLoading] = useState(false);
  const [avNumero, setAvNumero] = useState("");
  const [avSerie, setAvSerie] = useState("");
  const [avTipoMov, setAvTipoMov] = useState<string | null>(null);
  const [avDtEmissao, setAvDtEmissao] = useState<string | null>(todayISO());
  const [avValor, setAvValor] = useState("");
  const [avParcelas, setAvParcelas] = useState("1");
  const [avDtVenc, setAvDtVenc] = useState<string | null>(todayISO());
  const [avObs, setAvObs] = useState("");

  // ---- Detalhe / parcelas ----
  const [detalheOpen, setDetalheOpen] = useState(false);
  const [detalheLoading, setDetalheLoading] = useState(false);
  const [detalhe, setDetalhe] = useState<Detalhe | null>(null);
  const [excluindo, setExcluindo] = useState(false);

  // ---- Baixa manual de 1 parcela ----
  const [baixaVenc, setBaixaVenc] = useState<Parcela | null>(null);
  const [baixaData, setBaixaData] = useState<string | null>(todayISO());
  const [baixaValor, setBaixaValor] = useState("");
  const [baixaDesconto, setBaixaDesconto] = useState("");
  const [baixaJuros, setBaixaJuros] = useState("");
  const [baixando, setBaixando] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number" ? cod : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      const master = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(master ? -2 : (typeof vCod === "number" ? vCod : -2));
      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (!conn) return;
    (async () => {
      try {
        const j = await apiGet(conn, "/api/contas-receber-tipos-mov");
        if (j?.success) setTiposMov((j.items || []).map((i: any) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })));
      } catch { /* combo fica vazio, não trava a tela */ }
    })();
  }, [conn]);

  const carregar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    try {
      const qs: string[] = [];
      if (situacao) qs.push(`situacao=${encodeURIComponent(situacao)}`);
      if (busca.trim()) qs.push(`busca=${encodeURIComponent(busca.trim())}`);
      if (usarPeriodo && dataIni && dataFim) {
        qs.push(`data_ini=${encodeURIComponent(dataIni)}`);
        qs.push(`data_fim=${encodeURIComponent(dataFim)}`);
      }
      const j = await apiGet(conn, `/api/contas-receber${qs.length ? `?${qs.join("&")}` : ""}`);
      if (j?.success) {
        setItems(j.items || []);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, situacao, busca, usarPeriodo, dataIni, dataFim, feedback]);

  useEffect(() => { if (conn) carregar(); }, [conn, carregar]);

  // ---- Busca de cliente (avulso) ----
  useEffect(() => {
    if (!avClienteSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setAvClienteLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(avClienteTerm)}`;
        const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
        const j = await r.json();
        setAvClienteResults(j?.items || []);
      } catch { setAvClienteResults([]); } finally { setAvClienteLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [avClienteTerm, avClienteSearchOpen, conn]);

  const abrirAvulso = () => {
    setAvClienteCod(null); setAvClienteNome(""); setAvNumero(""); setAvSerie("");
    setAvTipoMov(null); setAvDtEmissao(todayISO()); setAvValor(""); setAvParcelas("1");
    setAvDtVenc(todayISO()); setAvObs("");
    setAvulsoOpen(true);
  };

  const salvarAvulso = useCallback(async () => {
    if (!conn) return;
    if (!avClienteCod) { feedback.showError("Selecione o cliente."); return; }
    if (!avNumero.trim() || !/^\d+$/.test(avNumero.trim())) { feedback.showError("Informe um número válido."); return; }
    if (!avTipoMov) { feedback.showError("Selecione o Tipo de Movimentação."); return; }
    const valorNum = parseNum(avValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor."); return; }
    const parcelasNum = parseInt(avParcelas || "1", 10) || 1;
    if (!avDtVenc) { feedback.showError("Informe a data do 1º vencimento."); return; }

    setSalvandoAvulso(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/avulsa", "POST", {
        cliente: avClienteCod, numero: parseInt(avNumero.trim(), 10), serie: avSerie.trim(),
        tipo_mov: avTipoMov, dt_emissao: avDtEmissao, valor: valorNum, parcelas: parcelasNum,
        dt_primeiro_vencimento: avDtVenc, observacao: avObs,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Duplicata lançada com sucesso.");
        setAvulsoOpen(false);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível lançar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setSalvandoAvulso(false);
    }
  }, [conn, avClienteCod, avNumero, avSerie, avTipoMov, avDtEmissao, avValor, avParcelas, avDtVenc, avObs, usuarioCod, classePerm, feedback, carregar]);

  const abrirDetalhe = useCallback(async (codigo: number) => {
    if (!conn) return;
    setDetalheOpen(true);
    setDetalheLoading(true);
    setDetalhe(null);
    try {
      const j = await apiGet(conn, `/api/contas-receber/${codigo}`);
      if (j?.success) {
        setDetalhe({ header: j.header, parcelas: j.parcelas || [], notas: j.notas || [] });
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível carregar o detalhe."));
        setDetalheOpen(false);
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
      setDetalheOpen(false);
    } finally {
      setDetalheLoading(false);
    }
  }, [conn, feedback]);

  const excluirDuplicata = useCallback(async () => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Excluir a duplicata #${detalhe.header.duplicata}? Esta ação não pode ser desfeita.`,
      async () => {
        setExcluindo(true);
        try {
          const j = await apiSend(conn, "/api/contas-receber/excluir", "POST", {
            codigo_duplicata: detalhe.header.codigo, usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
          });
          if (j?.success) {
            feedback.showSuccess("Duplicata excluída.");
            setDetalheOpen(false);
            carregar();
          } else {
            feedback.showError(friendlyApiError(j, "Não foi possível excluir."));
          }
        } catch (e) {
          feedback.showError(friendlyCatchError(e));
        } finally {
          setExcluindo(false);
        }
      },
    );
  }, [conn, detalhe, usuarioCod, classePerm, feedback, carregar]);

  const abrirBaixa = (p: Parcela) => {
    setBaixaVenc(p);
    setBaixaData(todayISO());
    setBaixaValor(String(p.valor).replace(".", ","));
    setBaixaDesconto(""); setBaixaJuros("");
  };

  const confirmarBaixa = useCallback(async () => {
    if (!conn || !baixaVenc || !detalhe) return;
    const valorNum = parseNum(baixaValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor pago."); return; }
    if (!baixaData) { feedback.showError("Informe a data do pagamento."); return; }
    setBaixando(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/baixar", "POST", {
        codigo_venc: baixaVenc.codigo, data_pag: baixaData, valor_pag: valorNum,
        desconto_pag: parseNum(baixaDesconto || "0"), juros_pag: parseNum(baixaJuros || "0"),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Baixa registrada.");
        setBaixaVenc(null);
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível dar baixa."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBaixando(false);
    }
  }, [conn, baixaVenc, baixaValor, baixaData, baixaDesconto, baixaJuros, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contas a Receber está disponível apenas no web." testID="contas-receber-web-only" />;
  }
  if (!loading && !can("CONTAS_RECEBER.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Contas a Receber." testID="contas-receber-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="contas-receber-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Contas a Receber</Text>
        {can("CONTAS_RECEBER.GRAVAR") || masterPerm ? (
          <IconButtonWithTooltip icon="add-circle-outline" label="Lançamento avulso" color={colors.onBrandPrimary} onPress={abrirAvulso} testID="contas-receber-avulso-btn" />
        ) : null}
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary} onPress={() => setAjudaOpen(true)} testID="contas-receber-ajuda-btn" />
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : (
            <View style={{ gap: spacing.md }}>
              <AccordionSection title="Buscar e Filtrar" defaultExpanded>
                <View style={{ gap: spacing.sm }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                    {SITUACOES.map((s) => (
                      <Pressable
                        key={s.key} onPress={() => setSituacao(s.key)}
                        style={[chipStyle(), situacao === s.key && chipSelStyle()]}
                        testID={`contas-receber-chip-${s.key || "todas"}`}
                      >
                        <Text style={[chipTextStyle(), situacao === s.key && chipTextSelStyle()]}>{s.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" }}>
                    <View style={{ flex: 1, minWidth: 220 }}>
                      <Text style={fieldLabel()}>Buscar por cliente ou nº da duplicata</Text>
                      <TextInput value={busca} onChangeText={setBusca} style={inputStyle()} testID="contas-receber-busca" onSubmitEditing={carregar} />
                    </View>
                    <Pressable onPress={() => setUsarPeriodo((v) => !v)} style={[chipStyle(), usarPeriodo && chipSelStyle(), { marginBottom: 2 }]}>
                      <Text style={[chipTextStyle(), usarPeriodo && chipTextSelStyle()]}>Filtrar por vencimento</Text>
                    </Pressable>
                    {usarPeriodo ? (
                      <>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>De</Text>
                          <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="contas-receber-data-ini" />
                        </View>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>Até</Text>
                          <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="contas-receber-data-fim" />
                        </View>
                      </>
                    ) : null}
                    <Pressable onPress={carregar} disabled={buscando} style={[secondaryBtnStyle(), { alignSelf: "flex-end" }]} testID="contas-receber-buscar-btn">
                      {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                        <><Ionicons name="search" size={16} color={colors.brandPrimary} /><Text style={secondaryBtnLabelStyle()}>Buscar</Text></>
                      )}
                    </Pressable>
                  </View>
                </View>
              </AccordionSection>

              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Duplicatas ({items.length})</Text>
                {items.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhuma duplicata encontrada.</Text>
                ) : (
                  items.map((it) => (
                    <Pressable key={it.codigo} onPress={() => abrirDetalhe(it.codigo)} style={itemRowStyle()} testID={`contas-receber-item-${it.codigo}`}>
                      <View style={[situacaoDotStyle(), { backgroundColor: it.vencido ? colors.error : it.situacao === "PG" ? colors.success : colors.brandPrimary }]} />
                      <View style={{ flex: 1, marginLeft: spacing.sm }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: it.vencido ? colors.error : colors.onSurface }}>
                          Duplicata #{it.duplicata}{it.desmembramento ? `/${it.desmembramento}` : ""}{"  ·  "}{it.cliente_nome}
                        </Text>
                        <Text style={{ fontSize: 12, color: it.vencido ? colors.error : colors.muted }}>
                          {formatDateBR(it.dt_emissao)}{it.proximo_vencimento ? ` · Próx. venc. ${formatDateBR(it.proximo_vencimento)}${it.vencido ? " (vencido)" : ""}` : ""}
                          {" · "}{it.parcelas_pagas}/{it.num_parcelas} paga(s)
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>{formatBRL(it.valor)}</Text>
                        {it.situacao !== "PG" ? <Text style={{ fontSize: 11, color: colors.muted }}>Em aberto: {formatBRL(it.valor_em_aberto)}</Text> : null}
                      </View>
                    </Pressable>
                  ))
                )}
              </View>
            </View>
          )}
        </View>
      </ScrollView>

      {/* ---- Modal: Lançamento avulso ---- */}
      <Modal visible={avulsoOpen} transparent animationType="slide" onRequestClose={() => setAvulsoOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setAvulsoOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <View style={ps.modalHeader}>
                <Text style={ps.modalTitle}>Lançamento Avulso</Text>
                <Pressable onPress={() => setAvulsoOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <View style={{ gap: spacing.sm }}>
                <View>
                  <Text style={fieldLabel()}>Cliente *</Text>
                  <Pressable onPress={() => setAvClienteSearchOpen(true)} style={[inputStyle(), { justifyContent: "center" }]} testID="contas-receber-avulso-cliente-btn">
                    <Text style={{ color: avClienteNome ? colors.onSurface : colors.muted }}>{avClienteNome || "Buscar cliente…"}</Text>
                  </Pressable>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 120 }}>
                    <Text style={fieldLabel()}>Número *</Text>
                    <TextInput value={avNumero} onChangeText={setAvNumero} keyboardType="numeric" style={inputStyle()} testID="contas-receber-avulso-numero" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Série</Text>
                    <TextInput value={avSerie} onChangeText={setAvSerie} style={inputStyle()} testID="contas-receber-avulso-serie" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Tipo de Movimentação *</Text>
                    <SelectField value={avTipoMov} onChange={(v) => setAvTipoMov(v as string)} options={tiposMov} compactWeb testID="contas-receber-avulso-tipomov" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Data de Emissão</Text>
                    <WebDateField value={avDtEmissao} onChange={(v) => setAvDtEmissao(v || null)} testID="contas-receber-avulso-dtemissao" />
                  </View>
                  <View style={{ width: 130 }}>
                    <Text style={fieldLabel()}>Valor *</Text>
                    <TextInput value={avValor} onChangeText={setAvValor} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-avulso-valor" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Parcelas</Text>
                    <TextInput value={avParcelas} onChangeText={setAvParcelas} keyboardType="numeric" style={inputStyle()} testID="contas-receber-avulso-parcelas" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>1º Vencimento *</Text>
                    <WebDateField value={avDtVenc} onChange={(v) => setAvDtVenc(v || null)} testID="contas-receber-avulso-dtvenc" />
                  </View>
                </View>
                <Text style={[fieldLabel(), { fontStyle: "italic" }]}>
                  Com mais de 1 parcela, o valor é dividido igualmente (a última absorve o arredondamento) e o vencimento avança 1 mês por parcela.
                </Text>
                <View>
                  <Text style={fieldLabel()}>Observação</Text>
                  <TextInput value={avObs} onChangeText={setAvObs} style={[inputStyle(), { minHeight: 60 }]} multiline testID="contas-receber-avulso-obs" />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setAvulsoOpen(false)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={salvarAvulso} disabled={salvandoAvulso} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-avulso-salvar">
                    {salvandoAvulso ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <ClientSearchModal
        visible={avClienteSearchOpen} onClose={() => setAvClienteSearchOpen(false)}
        term={avClienteTerm} setTerm={setAvClienteTerm} loading={avClienteLoading} results={avClienteResults}
        onPick={(c) => { setAvClienteCod(Number(c.codigo)); setAvClienteNome(c.nome); setAvClienteSearchOpen(false); }}
        onCreate={() => setAvClienteSearchOpen(false)}
      />

      {/* ---- Modal: Detalhe da duplicata ---- */}
      <Modal visible={detalheOpen} transparent animationType="slide" onRequestClose={() => setDetalheOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setDetalheOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            {detalheLoading || !detalhe ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 40 }} />
            ) : (
              <ScrollView>
                <View style={ps.modalHeader}>
                  <Text style={ps.modalTitle}>Duplicata #{detalhe.header.duplicata}{detalhe.header.desmembramento ? `/${detalhe.header.desmembramento}` : ""}</Text>
                  <Pressable onPress={() => setDetalheOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
                </View>
                <Text style={{ fontSize: 14, color: colors.onSurface, marginBottom: 4 }}>{detalhe.header.cliente_nome}</Text>
                <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.md }}>
                  Emissão {formatDateBR(detalhe.header.dt_emissao)} · Valor total {formatBRL(detalhe.header.valor)}
                </Text>

                <Text style={labelStyle()}>Parcelas</Text>
                {detalhe.parcelas.map((p) => (
                  <View key={p.codigo} style={parcelaRowStyle()}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
                        Parcela {p.desmembramento} · {formatBRL(p.valor)}
                      </Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>
                        Venc. {formatDateBR(p.dt_vencimento)}
                        {p.situacao === "PG" ? ` · Pago em ${formatDateBR(p.data_pag)} (${formatBRL(p.valor_pag || 0)})` : " · Aberto"}
                      </Text>
                    </View>
                    {p.situacao !== "PG" && (can("CONTAS_RECEBER.BAIXAR") || masterPerm) ? (
                      <Pressable onPress={() => abrirBaixa(p)} style={smallBtnStyle()} testID={`contas-receber-baixar-${p.codigo}`}>
                        <Ionicons name="checkmark-done-outline" size={14} color={colors.brandPrimary} />
                        <Text style={smallBtnLabelStyle()}>Baixar</Text>
                      </Pressable>
                    ) : p.situacao === "PG" ? (
                      <View style={[situacaoBadgeStyle(), { backgroundColor: colors.success + "22" }]}>
                        <Text style={[situacaoBadgeTextStyle(), { color: colors.success }]}>Pago</Text>
                      </View>
                    ) : null}
                  </View>
                ))}

                {(can("CONTAS_RECEBER.EXCLUIR") || masterPerm) ? (
                  <Pressable onPress={excluirDuplicata} disabled={excluindo} style={[ps.secondaryBtn, { marginTop: spacing.lg, borderColor: colors.error }]} testID="contas-receber-excluir-btn">
                    {excluindo ? <ActivityIndicator color={colors.error} size="small" /> : (
                      <><Ionicons name="trash-outline" size={16} color={colors.error} /><Text style={{ color: colors.error, fontWeight: "600" }}>Excluir Duplicata</Text></>
                    )}
                  </Pressable>
                ) : null}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* ---- Modal: Baixar parcela ---- */}
      <Modal visible={!!baixaVenc} transparent animationType="slide" onRequestClose={() => setBaixaVenc(null)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setBaixaVenc(null)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Dar Baixa</Text>
              <Pressable onPress={() => setBaixaVenc(null)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <View style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ width: 150 }}>
                  <Text style={fieldLabel()}>Data do Pagamento *</Text>
                  <WebDateField value={baixaData} onChange={(v) => setBaixaData(v || null)} testID="contas-receber-baixa-data" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Valor Pago *</Text>
                  <TextInput value={baixaValor} onChangeText={setBaixaValor} keyboardType="numeric" style={inputStyle()} testID="contas-receber-baixa-valor" />
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Desconto</Text>
                  <TextInput value={baixaDesconto} onChangeText={setBaixaDesconto} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-desconto" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Juros/Multa</Text>
                  <TextInput value={baixaJuros} onChangeText={setBaixaJuros} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-juros" />
                </View>
              </View>
              <View style={ps.modalBtns}>
                <Pressable onPress={() => setBaixaVenc(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                <Pressable onPress={confirmarBaixa} disabled={baixando} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-baixa-confirmar">
                  {baixando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Confirmar Baixa</Text>}
                </Pressable>
              </View>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Contas a Receber" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

function headerStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary };
}
function headerTitleStyle() {
  return { flex: 1, fontSize: 17, fontWeight: "700" as const, color: colors.onBrandPrimary };
}
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 };
}
function fieldLabel() {
  return { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const };
}
function inputStyle() {
  return { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.sm, paddingVertical: 10, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary } as const;
}
function itemRowStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border };
}
function situacaoDotStyle() {
  return { width: 8, height: 8, borderRadius: 4 };
}
function chipStyle() {
  return { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface };
}
function chipSelStyle() {
  return { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary };
}
function chipTextStyle() {
  return { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface };
}
function chipTextSelStyle() {
  return { color: colors.onBrandPrimary };
}
function secondaryBtnStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 100 };
}
function secondaryBtnLabelStyle() {
  return { color: colors.brandPrimary, fontWeight: "600" as const, fontSize: 14 };
}
function parcelaRowStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border };
}
function smallBtnStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, gap: 4, paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary };
}
function smallBtnLabelStyle() {
  return { fontSize: 12, fontWeight: "600" as const, color: colors.brandPrimary };
}
function situacaoBadgeStyle() {
  return { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill };
}
function situacaoBadgeTextStyle() {
  return { fontSize: 10, fontWeight: "700" as const };
}
