// Inutilização de Faixa NFe — migração de `Geral\FrmTraINF.frm`, lado NFe
// (Option1/"Tipo: NFe" da fonte). O lado NFC-e já existe como ação própria
// dentro de "Gestor NFCe" (`gestor-nfce.tsx`) — ver
// `backend/services/inutilizacao_nfe_service.py` e PENDENCIAS.md >
// "Inutilização de Faixa NFe" pro racional completo, inclusive o bug real
// de schema encontrado e corrigido em `inutilizacao_nfe` (tabela
// compartilhada com o lado NFC-e) ao construir esta tela.
//
// Diferença real vs. NFC-e: a checagem de "faixa já emitida" aqui é 100%
// local (consulta `n_fiscal`), sem consultar o SEFAZ número a número antes
// — fiel à fonte (`Command1_Click`, ramo NFe).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField from "@/src/components/SelectField";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { showApoioFiscalError } from "@/src/utils/apoioFiscal";
import ApoioFiscalBackOnModal, { ApoioFiscalInfo } from "@/src/components/ApoioFiscalBackOnModal";

type Serie = { serie: string; ultimo_numero: number };
type HistoricoItem = {
  codauto_inutilizacao: number;
  numero_inicial: number;
  numero_final: number;
  serie: string;
  motivo: string;
  protocolo_sefaz: string | null;
  data_registro: string | null;
  usuario: string | null;
};

const INUTIL_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "O que é inutilização de faixa",
    texto: "Formaliza junto à SEFAZ que uma faixa de números de NF-e não vai ser usada (ex.: pulou números por engano) — é diferente de cancelar uma nota já emitida.",
    icon: { lib: "ion", name: "close-circle-outline" },
  },
  {
    titulo: "Processo é irreversível",
    texto: "A SEFAZ não permite desfazer uma inutilização — confira os números com atenção antes de confirmar.",
    icon: { lib: "ion", name: "warning-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Faixa com nota emitida bloqueia",
    texto: "Se algum número dentro da faixa já tiver uma NF-e emitida, a inutilização é bloqueada e os números encontrados são listados.",
    icon: { lib: "ion", name: "list-outline" },
  },
];

export default function InutilizacaoNfeScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Inutilização de Faixa NFe está disponível apenas no web." testID="inutilizacao-nfe-web-only" />;
  }

  const canAbrir = can("INUTIL_NFE.ABRIR") || isMaster;
  const canGravar = can("INUTIL_NFE.GRAVAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [processando, setProcessando] = useState(false);
  const [apoioFiscalInfo, setApoioFiscalInfo] = useState<ApoioFiscalInfo | null>(null);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);

  const [series, setSeries] = useState<Serie[]>([]);
  const [serie, setSerie] = useState<string | null>(null);
  const [numeroInicial, setNumeroInicial] = useState("");
  const [numeroFinal, setNumeroFinal] = useState("");
  const [motivo, setMotivo] = useState("");

  const [historico, setHistorico] = useState<HistoricoItem[]>([]);

  const ensureConn = useCallback(async (): Promise<Connection | null> => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
    if (c) setConn(c);
    return c;
  }, [conn, router]);

  const carregar = useCallback(async () => {
    const c = await ensureConn();
    if (!c) return;
    setCarregando(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const base = c.api.replace(/\/+$/, "");
      const [rSeries, rHist] = await Promise.all([
        fetch(`${base}/api/inutilizacao-nfe/series?${qs}`),
        fetch(`${base}/api/inutilizacao-nfe/historico?${qs}`),
      ]);
      const jSeries = await rSeries.json();
      const jHist = await rHist.json();
      if (jSeries?.success) {
        setSeries(jSeries.series || []);
        if (!serie && jSeries.series?.length === 1) setSerie(jSeries.series[0].serie);
      } else {
        fb.showError(friendlyApiError(jSeries, "Não foi possível carregar as séries de NF-e."));
      }
      if (jHist?.success) setHistorico(jHist.historico || []);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setCarregando(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ensureConn, fb]);

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const executarInutilizacao = async () => {
    const c = await ensureConn();
    if (!c) return;
    setProcessando(true);
    try {
      const body = {
        servidor: c.servidor, banco: c.banco, serie, numero_inicial: Number(numeroInicial), numero_final: Number(numeroFinal),
        motivo: motivo.trim(), usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/inutilizacao-nfe/inutilizar`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(`Faixa inutilizada — protocolo SEFAZ ${j.protocolo_sefaz || "-"}.`, undefined, 5000);
        setNumeroInicial("");
        setNumeroFinal("");
        setMotivo("");
        carregar();
      } else {
        const info = showApoioFiscalError(fb, j, "Não foi possível inutilizar a faixa.", 5000);
        if (info) setApoioFiscalInfo(info);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setProcessando(false);
    }
  };

  const confirmarInutilizacao = () => {
    if (!serie) { fb.showWarning("Selecione a série."); return; }
    const ini = Number(numeroInicial);
    const fim = Number(numeroFinal);
    if (!numeroInicial || !numeroFinal || Number.isNaN(ini) || Number.isNaN(fim)) {
      fb.showWarning("Defina corretamente o Número Inicial e o Número Final.");
      return;
    }
    if (fim < ini) { fb.showWarning("Número Final não pode ser menor que o Número Inicial."); return; }
    if (motivo.trim().length < 15) { fb.showWarning("Informe um motivo com pelo menos 15 caracteres."); return; }
    if (motivo.trim().length > 50) { fb.showWarning("O motivo pode ter no máximo 50 caracteres."); return; }

    fb.showConfirm(
      "Confira as informações com atenção — a SEFAZ não disponibiliza cancelamento para este processo!",
      () => {
        fb.showConfirm(
          `Confirma a inutilização da faixa ${numeroInicial} a ${numeroFinal}, série ${serie}?`,
          executarInutilizacao,
          { title: "Confirmar inutilização", confirmText: "Confirmar", destructive: true },
        );
      },
      { title: "Atenção", confirmText: "Continuar", destructive: true },
    );
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Inutilização de Faixa NFe." testID="inutilizacao-nfe-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="inutilizacao-nfe-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Inutilização de Faixa NFe</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="inutilizacao-nfe-ajuda"
        />
      </View>

      {carregando ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Nova inutilização</Text>

              <View style={styles.rowFields}>
                <View style={styles.colSerie}>
                  <Text style={styles.fieldLabel}>Série</Text>
                  <SelectField
                    value={serie}
                    onChange={(v) => setSerie(v as string | null)}
                    options={series.map((s) => ({ value: s.serie, label: `${s.serie} (último: ${s.ultimo_numero})` }))}
                    placeholder="Selecione"
                    compactWeb
                    testID="inutilizacao-nfe-serie"
                  />
                </View>
                <View style={styles.colNum}>
                  <Text style={styles.fieldLabel}>Número Inicial</Text>
                  <TextInput
                    value={numeroInicial} onChangeText={setNumeroInicial} keyboardType="numeric"
                    style={styles.numInput} testID="inutilizacao-nfe-numero-inicial"
                  />
                </View>
                <View style={styles.colNum}>
                  <Text style={styles.fieldLabel}>Número Final</Text>
                  <TextInput
                    value={numeroFinal} onChangeText={setNumeroFinal} keyboardType="numeric"
                    style={styles.numInput} testID="inutilizacao-nfe-numero-final"
                  />
                </View>
              </View>

              <Text style={styles.fieldLabel}>Motivo (15 a 50 caracteres)</Text>
              <TextInput
                value={motivo} onChangeText={setMotivo} multiline numberOfLines={2} maxLength={50}
                style={styles.textArea} testID="inutilizacao-nfe-motivo"
              />
              <Text style={styles.charCount}>{motivo.trim().length}/50</Text>

              {canGravar ? (
                <Pressable onPress={confirmarInutilizacao} disabled={processando} style={styles.primaryBtn} testID="inutilizacao-nfe-inutilizar">
                  {processando ? <ActivityIndicator color="#fff" size="small" /> : (
                    <><Ionicons name="close-circle-outline" size={16} color="#fff" /><Text style={styles.primaryBtnText}>{processando ? "Inutilizando…" : "Inutilizar"}</Text></>
                  )}
                </Pressable>
              ) : null}
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Histórico</Text>
              {historico.length === 0 ? (
                <Text style={styles.hint}>Nenhuma inutilização de NF-e registrada ainda.</Text>
              ) : (
                historico.map((h) => (
                  <View key={h.codauto_inutilizacao} style={styles.histRow} testID={`inutilizacao-nfe-hist-${h.codauto_inutilizacao}`}>
                    <Text style={styles.histTitulo}>Série {h.serie} — {h.numero_inicial} a {h.numero_final}</Text>
                    <Text style={styles.hint}>{h.motivo}</Text>
                    <Text style={styles.hint}>Protocolo: {h.protocolo_sefaz || "-"} · {h.data_registro || "-"} · {h.usuario || "-"}</Text>
                  </View>
                ))
              )}
            </View>
          </View>
        </ScrollView>
      )}

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Inutilização de Faixa NFe" itens={INUTIL_AJUDA_ITENS} />
      <ApoioFiscalBackOnModal visible={!!apoioFiscalInfo} info={apoioFiscalInfo} onClose={() => setApoioFiscalInfo(null)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },

  scroll: { paddingBottom: spacing.xxxl, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: { ...WEB_CONTENT_SHELL, maxWidth: 640, gap: spacing.md },
  card: { ...WEB_FILTER_CARD },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  hint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  fieldLabel: { fontSize: 11, color: colors.muted, marginTop: spacing.sm, marginBottom: 4 },

  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  colSerie: { minWidth: 180, flexGrow: 1 },
  colNum: { width: 130 },
  numInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface },

  textArea: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface, minHeight: 56, textAlignVertical: "top" },
  charCount: { fontSize: 10, color: colors.muted, textAlign: "right", marginTop: 2 },

  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingVertical: 12, marginTop: spacing.lg },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 14 },

  histRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: spacing.sm },
  histTitulo: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
});
