// Contingência NFe — migração de `Geral\FrmConNFe.frm`. Ver
// `backend/services/contingencia_nfe_service.py` e PENDENCIAS.md
// (blueprint item 7) pro racional completo — mesma "infraestrutura
// mínima" já usada em Contingência NFCe (embutida no Gestor NFCe), mas
// como tela própria (não há um "Gestor NFe" único pra embutir).
//
// Diferença real vs. NFCe: os DOIS tipos (FS-IA/FS-DA) são igualmente
// selecionáveis ao abrir — não um tipo fixo.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";

type StatusContingencia = {
  aberta: boolean;
  data_inicio?: string;
  hora_inicio?: string;
  motivo?: string;
  tipo_contingencia?: number;
};

const CONTINGENCIA_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "O que é contingência",
    texto: "Quando o SEFAZ está fora do ar e não é possível transmitir NF-e normalmente, abra uma contingência aqui — as novas notas ficam registradas localmente até você fechar a contingência.",
    icon: { lib: "ion", name: "cloud-offline-outline" },
  },
  {
    titulo: "FS-IA x FS-DA",
    texto: "Dois formatos de Formulário de Segurança aceitos pela SEFAZ para imprimir o documento em contingência — FS-IA (Impressor Autônomo) ou FS-DA (Documento Auxiliar). Confirme com seu contador qual o seu estabelecimento usa.",
    icon: { lib: "ion", name: "document-text-outline" },
  },
  {
    titulo: "Fechar contingência",
    texto: "Assim que o SEFAZ voltar, feche a contingência aqui — isso não retransmite nada automaticamente ainda, é só o registro de quando o período terminou.",
    icon: { lib: "ion", name: "checkmark-circle-outline" },
    cor: colors.warning,
  },
];

export default function ContingenciaNfeScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contingência NFe está disponível apenas no web." testID="contingencia-nfe-web-only" />;
  }

  const canAbrir = can("CONT_NFE.ABRIR") || isMaster;
  const canGravar = can("CONT_NFE.GRAVAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [processando, setProcessando] = useState(false);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);
  const [status, setStatus] = useState<StatusContingencia>({ aberta: false });

  const [motivo, setMotivo] = useState("");
  const [tipo, setTipo] = useState<2 | 5>(2);

  const ensureConn = useCallback(async (): Promise<Connection | null> => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
    if (c) setConn(c);
    return c;
  }, [conn, router]);

  const carregarStatus = useCallback(async () => {
    const c = await ensureConn();
    if (!c) return;
    setCarregando(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/contingencia-nfe/status?${qs}`);
      const j = await r.json();
      if (j?.success) setStatus(j);
      else fb.showError(friendlyApiError(j, "Não foi possível consultar a contingência."));
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setCarregando(false);
    }
  }, [ensureConn, fb]);

  useEffect(() => {
    carregarStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const abrir = async () => {
    if (motivo.trim().length < 15) { fb.showWarning("Informe um motivo com pelo menos 15 caracteres."); return; }
    const c = await ensureConn();
    if (!c) return;
    setProcessando(true);
    try {
      const body = {
        servidor: c.servidor, banco: c.banco, motivo: motivo.trim(), tipo_contingencia: tipo,
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/contingencia-nfe/abrir`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Contingência aberta.", undefined, 5000);
        setMotivo("");
        carregarStatus();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível abrir a contingência."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setProcessando(false);
    }
  };

  const fechar = async () => {
    const c = await ensureConn();
    if (!c) return;
    setProcessando(true);
    try {
      const body = { servidor: c.servidor, banco: c.banco, usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster };
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/contingencia-nfe/fechar`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Contingência fechada.", undefined, 5000);
        carregarStatus();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível fechar a contingência."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setProcessando(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Contingência NFe." testID="contingencia-nfe-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contingencia-nfe-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Contingência NFe</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="contingencia-nfe-ajuda"
        />
      </View>

      {carregando ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShell}>
            {status.aberta ? (
              <View style={[styles.card, styles.cardAberta]} testID="contingencia-nfe-status-aberta">
                <View style={styles.statusRow}>
                  <Ionicons name="alert-circle" size={22} color={colors.warning} />
                  <Text style={styles.statusTitulo}>Contingência aberta</Text>
                </View>
                <Text style={styles.hint}>Início: {status.data_inicio} {status.hora_inicio}</Text>
                <Text style={styles.hint}>Tipo: {status.tipo_contingencia === 5 ? "FS-DA (Documento Auxiliar)" : "FS-IA (Impressor Autônomo)"}</Text>
                <Text style={styles.hint}>Motivo: {status.motivo}</Text>
                {canGravar ? (
                  <Pressable onPress={fechar} disabled={processando} style={styles.primaryBtn} testID="contingencia-nfe-fechar">
                    {processando ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="checkmark-circle-outline" size={16} color="#fff" /><Text style={styles.primaryBtnText}>Fechar Contingência</Text></>
                    )}
                  </Pressable>
                ) : null}
              </View>
            ) : (
              <View style={styles.card} testID="contingencia-nfe-status-fechada">
                <View style={styles.statusRow}>
                  <Ionicons name="checkmark-circle-outline" size={22} color={colors.brandPrimary} />
                  <Text style={styles.statusTitulo}>Nenhuma contingência aberta</Text>
                </View>

                <Text style={styles.fieldLabel}>Tipo</Text>
                <View style={styles.tipoRow}>
                  <Pressable onPress={() => setTipo(2)} style={[styles.tipoBtn, tipo === 2 && styles.tipoBtnSel]} testID="contingencia-nfe-tipo-fsia">
                    <Text style={[styles.tipoBtnText, tipo === 2 && styles.tipoBtnTextSel]}>FS-IA</Text>
                  </Pressable>
                  <Pressable onPress={() => setTipo(5)} style={[styles.tipoBtn, tipo === 5 && styles.tipoBtnSel]} testID="contingencia-nfe-tipo-fsda">
                    <Text style={[styles.tipoBtnText, tipo === 5 && styles.tipoBtnTextSel]}>FS-DA</Text>
                  </Pressable>
                </View>

                <Text style={styles.fieldLabel}>Motivo (mín. 15 caracteres)</Text>
                <TextInput
                  value={motivo} onChangeText={setMotivo} multiline numberOfLines={3}
                  style={styles.textArea} testID="contingencia-nfe-motivo"
                />

                {canGravar ? (
                  <Pressable onPress={abrir} disabled={processando} style={styles.primaryBtn} testID="contingencia-nfe-abrir">
                    {processando ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="alert-circle-outline" size={16} color="#fff" /><Text style={styles.primaryBtnText}>Abrir Contingência</Text></>
                    )}
                  </Pressable>
                ) : null}
              </View>
            )}
          </View>
        </ScrollView>
      )}

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Contingência NFe" itens={CONTINGENCIA_AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: { ...WEB_CONTENT_SHELL, maxWidth: 480 },
  card: { ...WEB_FILTER_CARD },
  cardAberta: { backgroundColor: colors.surfaceSecondary, borderColor: colors.warning },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  fieldLabel: { fontSize: 11, color: colors.muted, marginTop: spacing.md, marginBottom: 4 },

  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  statusTitulo: { fontSize: 15, fontWeight: "700", color: colors.onSurface },

  tipoRow: { flexDirection: "row", gap: spacing.sm },
  tipoBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingVertical: 10, alignItems: "center" },
  tipoBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  tipoBtnTextSel: { color: "#fff" },

  textArea: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface, minHeight: 72, textAlignVertical: "top" },

  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingVertical: 12, marginTop: spacing.lg },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 14 },
});
