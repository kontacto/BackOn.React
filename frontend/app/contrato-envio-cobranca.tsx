// Transações > Contratos > Envio de Cobrança — migração de
// Geral\FrmEnvCob.frm ("Envio de emails de cobrança"). Achado real
// 2026-08-25: as linhas de `cobrancas_enviadas` são criadas no momento
// do faturamento (Faturar Contratos), não por esta tela — aqui só
// consulta o que já foi lançado e envia. Motor de envio reaproveita
// `email_cobranca_service.py`, já testado com envio real.
//
// 2026-08-26: o e-mail sai com o comprovante em PDF anexado quando
// possível — Boleto anexa o boleto real (código de barras, ver
// backend/services/boleto_pdf_service.py) se o título já foi registrado
// num banco; Recibo anexa um recibo identificado pelo número da comanda
// (backend/services/recibo_pdf_service.py + contratos_service.
// _montar_recibo_para_anexo_sync, leitura pura, nunca grava em Recibos/
// Seq_Recibo — resposta de Leandro: "o controle já é o número da
// comanda"). Ver PENDENCIAS.md > "Envio de Cobrança de Contratos" e
// "Boleto em PDF".
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;

type ItemCobranca = {
  codigo: number; contrato: number; contrato_texto: string; comanda: number;
  ano_referencia: number; mes_referencia: number; vencimento: string | null;
  cliente: number; cliente_nome: string; email_destino: string;
  data_envio: string | null; hora_envio: string; status_envio: string; obs_envio: string;
  valor: number;
};

type ResultadoEnvio = { codigo: number; success: boolean; message?: string };

const STATUS_OPCOES = ["Não Enviado", "Sem Email cadastrado", "Falha ao Enviar", "Enviado com Sucesso"];

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "Mês/Ano ou Período", texto: "Use Mês/Ano de referência pra ver as cobranças de uma mensalidade específica, ou Período (De/Até) pra ver por data da comanda faturada — preencher o período tem prioridade sobre Mês/Ano.", icon: { lib: "ion", name: "calendar-outline" } },
  { titulo: "Situação do Envio", texto: "\"Não Enviado\" é o normal pra cobrança recém-lançada. \"Sem Email cadastrado\" significa que o cliente não tem e-mail no cadastro — corrija o cadastro antes de tentar de novo. \"Falha ao Enviar\" costuma ser problema de configuração de SMTP (Controle do Sistema).", icon: { lib: "ion", name: "information-circle-outline" } },
  { titulo: "Enviar Selecionadas", texto: "Envia um e-mail avisando sobre a mensalidade pra cada cobrança marcada, com um comprovante em PDF anexado automaticamente: contrato tipo Boleto anexa o boleto real, se o título já tiver sido registrado num banco (tela Geração de Boletos, em Financeiro > Cobranças); contrato tipo Recibo anexa um recibo identificado pelo número da comanda. Boleto ainda não registrado num banco segue sem anexo. O status de cada uma é atualizado automaticamente.", icon: { lib: "ion", name: "mail-outline" } },
];

function hojeIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ContratoEnvioCobrancaScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contratos está disponível apenas no web." testID="cec-web-only" />;
  }
  if (!moduleOn("contratos")) {
    return <LockedView title="Módulo desativado" message="O módulo Contratos está desligado em Configurações > Módulos e Recursos." testID="cec-module-off" />;
  }
  if (!can("ENVIO_COBRANCA.ABRIR")) {
    return <LockedView title="Sem permissão" message="Você não tem acesso a esta tela." testID="cec-no-perm" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (c) setConn(c);
      setLoadingConn(false);
    })();
  }, [router]);

  const hoje = new Date();
  const [ano, setAno] = useState(String(hoje.getFullYear()));
  const [mes, setMes] = useState(String(hoje.getMonth() + 1));
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [statusFiltro, setStatusFiltro] = useState<string[]>([]);

  const [items, setItems] = useState<ItemCobranca[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [buscando, setBuscando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [resultados, setResultados] = useState<ResultadoEnvio[]>([]);

  const toggleStatus = (s: string) => {
    setStatusFiltro((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  };

  const selecionar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    setResultados([]);
    try {
      const params: Record<string, string> = {};
      if (dataIni && dataFim) {
        params.data_ini = dataIni;
        params.data_fim = dataFim;
      } else {
        params.ano = ano;
        params.mes = mes;
      }
      if (statusFiltro.length > 0) params.status = statusFiltro.join(",");
      const j = await apiGet(conn, "/api/contratos/cobrancas", params);
      if (j?.success) {
        const novos: ItemCobranca[] = j.items || [];
        setItems(novos);
        setSelecionados(new Set(novos.map((i) => i.codigo)));
        if (novos.length === 0) fb.showInfo("Nenhuma cobrança encontrada para esse filtro.");
      } else {
        setItems([]);
        fb.showError(friendlyApiError(j, "Falha ao buscar cobranças."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao buscar cobranças."));
    } finally {
      setBuscando(false);
    }
  }, [conn, ano, mes, dataIni, dataFim, statusFiltro, fb]);

  const toggleSelecionado = (codigo: number) => {
    setSelecionados((cur) => {
      const next = new Set(cur);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };
  const marcarTodas = () => setSelecionados(new Set(items.map((i) => i.codigo)));
  const desmarcarTodas = () => setSelecionados(new Set());

  const enviar = useCallback(() => {
    if (!conn || selecionados.size === 0) return;
    fb.showConfirm(`Enviar e-mail de cobrança para ${selecionados.size} registro(s) selecionado(s)?`, async () => {
      setEnviando(true);
      try {
        const j = await apiSend(conn, "/api/contratos/cobrancas/enviar", "POST", { ...auditCtx, ids: Array.from(selecionados) });
        if (j?.success) {
          const novos: ResultadoEnvio[] = j.resultados || [];
          setResultados(novos);
          const ok = novos.filter((r) => r.success).length;
          const falhas = novos.length - ok;
          if (falhas > 0) fb.showError(`${ok} enviado(s), ${falhas} com falha — veja o detalhe na lista.`);
          else fb.showSuccess(`${ok} e-mail(s) de cobrança enviado(s) com sucesso.`);
          await selecionar();
        } else {
          fb.showError(friendlyApiError(j, "Falha ao enviar cobranças."));
        }
      } catch (e) {
        fb.showError(friendlyCatchError(e, "Falha ao enviar cobranças."));
      } finally {
        setEnviando(false);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, selecionados, auditCtx, fb, selecionar]);

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contrato-envio-cobranca-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back} testID="cec-voltar">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Envio de Cobrança</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} testID="cec-ajuda" />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <Text style={styles.sectionTitle}>Filtro</Text>
            <Text style={styles.helpText}>
              Preencher Período (De/Até) tem prioridade sobre Mês/Ano de referência — deixe o período
              vazio pra filtrar só por mês/ano.
            </Text>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Mês</Text>
                <TextInput value={mes} onChangeText={setMes} keyboardType="number-pad" maxLength={2} style={styles.input} testID="cec-mes" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Ano</Text>
                <TextInput value={ano} onChangeText={setAno} keyboardType="number-pad" maxLength={4} style={styles.input} testID="cec-ano" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Período De</Text>
                <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="cec-data-ini" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Período Até</Text>
                <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="cec-data-fim" />
              </View>
              {(dataIni || dataFim) ? (
                <Pressable onPress={() => { setDataIni(null); setDataFim(null); }} style={styles.linkBtn} testID="cec-limpar-periodo">
                  <Text style={styles.linkBtnText}>Limpar período</Text>
                </Pressable>
              ) : null}
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Situação do Envio</Text>
                <View style={styles.chipsRow}>
                  {STATUS_OPCOES.map((s) => (
                    <Pressable key={s} onPress={() => toggleStatus(s)} style={[styles.chip, statusFiltro.includes(s) && styles.chipSel]} testID={`cec-status-${s}`}>
                      <Text style={[styles.chipText, statusFiltro.includes(s) && styles.chipTextSel]}>{s}</Text>
                    </Pressable>
                  ))}
                </View>
                <Text style={styles.helpText}>Nenhuma marcada = todas as situações.</Text>
              </View>
            </View>
            <Pressable onPress={selecionar} disabled={buscando} style={[styles.actionBtn, styles.actionBtnPrimary]} testID="cec-selecionar">
              {buscando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.actionBtnPrimaryText}>Selecionar</Text>}
            </Pressable>
          </View>

          {items.length > 0 && (
            <View style={styles.filterCard}>
              <View style={styles.rowBetween}>
                <Text style={styles.sectionTitle}>Cobranças ({items.length})</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Pressable onPress={marcarTodas} style={styles.linkBtn}><Text style={styles.linkBtnText}>Marcar Todas</Text></Pressable>
                  <Pressable onPress={desmarcarTodas} style={styles.linkBtn}><Text style={styles.linkBtnText}>Desmarcar Todas</Text></Pressable>
                </View>
              </View>
              {items.map((it) => (
                <View key={it.codigo} style={styles.gridRow} testID={`cec-item-${it.codigo}`}>
                  <Pressable onPress={() => toggleSelecionado(it.codigo)} hitSlop={8} testID={`cec-sel-${it.codigo}`}>
                    <Ionicons name={selecionados.has(it.codigo) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  </Pressable>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowTitle}>#{it.contrato_texto || it.contrato} · {it.cliente_nome}</Text>
                    <Text style={styles.gridRowSub}>
                      {it.email_destino || "sem e-mail cadastrado"} · Venc. {it.vencimento ? formatDateBR(it.vencimento) : "—"} ·{" "}
                      <Text style={{ color: it.status_envio === "Enviado com Sucesso" ? colors.success : it.status_envio === "Falha ao Enviar" ? colors.error : colors.muted }}>
                        {it.status_envio}
                      </Text>
                    </Text>
                  </View>
                  <Text style={styles.gridRowValor}>{formatBRL(it.valor)}</Text>
                </View>
              ))}
              <View style={styles.divider} />
              <Pressable
                onPress={enviar}
                disabled={enviando || selecionados.size === 0 || !can("ENVIO_COBRANCA.ENVIAR")}
                style={[styles.actionBtn, styles.actionBtnPrimary]}
                testID="cec-enviar"
              >
                {enviando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.actionBtnPrimaryText}>Enviar Selecionadas</Text>}
              </Pressable>
              <Text style={styles.helpText}>
                Envia um e-mail de aviso pra cada cobrança marcada — sem anexo de Recibo/Boleto nesta
                versão da tela. Confira o e-mail cadastrado antes de enviar.
              </Text>
            </View>
          )}

          {resultados.length > 0 && (
            <View style={styles.filterCard}>
              <Text style={styles.sectionTitle}>Resultado do Envio</Text>
              {resultados.map((r) => (
                <View key={r.codigo} style={styles.gridRow} testID={`cec-resultado-${r.codigo}`}>
                  <Ionicons name={r.success ? "checkmark-circle" : "close-circle"} size={20} color={r.success ? colors.success : colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowTitle}>Cobrança #{r.codigo}</Text>
                    <Text style={[styles.gridRowSub, !r.success && { color: colors.error }]}>{r.message || (r.success ? "Enviado." : "Falha.")}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Envio de Cobrança" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary, gap: spacing.sm },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  helpText: { fontSize: 11, color: colors.muted, lineHeight: 15, marginTop: 2 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  filterCard: { ...WEB_FILTER_CARD, marginBottom: spacing.md, gap: spacing.sm },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  colTiny: { width: 70 },
  colNarrow: { width: 150 },
  colFlex: { flex: 1, minWidth: 220 },
  label: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  actionBtn: { paddingVertical: 10, paddingHorizontal: spacing.lg, borderRadius: radius.md, alignItems: "center", alignSelf: "flex-start" },
  actionBtnPrimary: { backgroundColor: colors.brandPrimary },
  actionBtnPrimaryText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  linkBtn: { paddingVertical: 6, paddingHorizontal: spacing.sm },
  linkBtnText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },
  gridRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  gridRowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  gridRowValor: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.sm },
});
