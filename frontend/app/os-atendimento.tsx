// Tela de Atendimento de Campo (Assistência Técnica — mobile) — ver
// AssistenciaTecnicaCampo.md. Versão ENXUTA, separada da O.S. Completa
// (`os-geral.tsx`, web-only): o técnico em campo só precisa ler o QR Code
// do equipamento (ou buscar pelo número de série na mão), fazer check-in/
// check-out por geolocalização, registrar os campos do equipamento
// atendido, preencher o Formulário Dinâmico (checklist) e fechar a O.S. —
// nunca vincula equipamento novo, isso continua exclusivo da retaguarda
// (O.S. Completa), ver regra 8 do documento.
//
// Reaproveita tal como estão (nenhuma mudança): `useOSEquipamentos`/
// `OSEquipamentoCard` (mesmos endpoints /api/os-completo/{os}/equipamentos
// já usados por os-geral.tsx — confirmado sem checagem de permissão no
// backend, ver PENDENCIAS.md) e `LayoutPreenchimentoModal` (Motor de
// Layout, entidade O.S.).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";

import { Ionicons } from "@/src/components/Ionicons";
import { colors, radius, spacing } from "@/src/theme/colors";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import { ToastTone } from "@/src/components/pedido/types";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { useOSEquipamentos } from "@/src/components/os/useOSEquipamentos";
import OSEquipamentoCard from "@/src/components/os/OSEquipamentoCard";
import LayoutPreenchimentoModal from "@/src/components/agenda/LayoutPreenchimentoModal";

const LAYOUT_ENTIDADE_OS = 7;

type OSAtendimentoData = {
  codigo: number;
  cliente_nome: string;
  situacao: string;
  situacao_label: string;
  resumo: string;
  descricao_cliente: string;
  status_os: number | null;
  status_os_descricao?: string;
  checkin_em: string | null;
  checkout_em: string | null;
};

type HistoricoItem = { codigo: number; data: string | null; situacao: string; resumo: string };

const AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Ler QR Code / Buscar",
    texto: "Aponte a câmera para o QR Code fixado no equipamento, ou digite o número de série na mão e toque em Buscar. Isso abre a OS que a retaguarda já preparou para este equipamento.",
    icon: { lib: "ion", name: "qr-code-outline" },
  },
  {
    titulo: "Fazer Check-in",
    texto: "Registra a hora e o local (GPS) de chegada no atendimento. Só é possível um check-in por OS — feito o check-in, os campos do equipamento ficam liberados para preenchimento.",
    icon: { lib: "ion", name: "log-in-outline" },
  },
  {
    titulo: "Status do equipamento",
    texto: "Situação atual do atendimento deste equipamento (ex.: Em execução, Executado). Pode ser alterada livremente pelo técnico durante a visita.",
    icon: { lib: "ion", name: "options-outline" },
  },
  {
    titulo: "Formulário Dinâmico",
    texto: "Checklist de atendimento (perguntas definidas pela empresa) — preencha durante a visita, se houver algum disponível para esta OS.",
    icon: { lib: "ion", name: "document-text-outline" },
  },
  {
    titulo: "Fechar O.S.",
    texto: "Encerra a OS quando o atendimento foi concluído com sucesso. Cancelar/Reabrir/Faturar continuam exclusivos da retaguarda.",
    icon: { lib: "ion", name: "checkmark-done-outline" },
  },
  {
    titulo: "Fazer Check-out",
    texto: "Registra a hora e o local (GPS) de saída do atendimento. Exige que o check-in já tenha sido feito nesta OS.",
    icon: { lib: "ion", name: "log-out-outline" },
  },
];

export default function OSAtendimentoScreen() {
  const router = useRouter();
  const feedback = useFeedback();
  const { can } = usePermissions();
  const params = useLocalSearchParams<{ os?: string; serie?: string }>();
  const osId = params.os ? parseInt(String(params.os), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [classe, setClasse] = useState<number | null>(null);
  const [bootLoading, setBootLoading] = useState(true);

  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: ToastTone = "info") => {
    setToast({ msg: m, tone: t });
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), 2500);
  }, []);

  const [ajudaOpen, setAjudaOpen] = useState(false);

  // ---------- estado "scanner" (sem ?os= na URL) ----------
  const [camPerm, requestCamPerm] = useCameraPermissions();
  const [scannerAtivo, setScannerAtivo] = useState(false);
  const scanLockRef = useRef(false);
  const [manualSerie, setManualSerie] = useState("");
  const [resolvendo, setResolvendo] = useState(false);

  const resolveSerie = useCallback(async (serie: string) => {
    const s = serie.trim();
    if (!conn || !s) return;
    setResolvendo(true);
    try {
      const j = await apiGet(conn, "/api/os/resolver-por-equipamento", { numero_de_serie: s });
      if (!j?.success) {
        showToast(friendlyApiError(j, "Equipamento não encontrado."), "error");
        return;
      }
      router.replace({ pathname: "/os-atendimento", params: { os: String(j.os_codigo), serie: s } });
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao buscar equipamento."), "error");
    } finally {
      setResolvendo(false);
      scanLockRef.current = false;
    }
  }, [conn, router, showToast]);

  const handleBarcodeScanned = useCallback((result: { data: string }) => {
    if (scanLockRef.current) return;
    const raw = (result?.data || "").trim();
    // Mesmo prefixo já usado por equipamentos_service.QRCODE_PREFIXO_EQUIPAMENTO.
    const serie = raw.startsWith("EQUIP:") ? raw.slice(6) : raw;
    if (!serie) return;
    scanLockRef.current = true;
    setScannerAtivo(false);
    resolveSerie(serie);
  }, [resolveSerie]);

  // ---------- estado "atendimento" (com ?os=) ----------
  const [os, setOs] = useState<OSAtendimentoData | null>(null);
  const [osLoading, setOsLoading] = useState(false);
  const [statusOsOptions, setStatusOsOptions] = useState<{ value: number; label: string }[]>([]);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [checkingIn, setCheckingIn] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [fechando, setFechando] = useState(false);
  const [formulariosOpen, setFormulariosOpen] = useState(false);

  const isAberta = os?.situacao === "A";
  const jaFezCheckin = !!os?.checkin_em;
  const jaFezCheckout = !!os?.checkout_em;

  const loadOs = useCallback(async () => {
    if (!conn || !osId) return;
    setOsLoading(true);
    try {
      const j = await apiGet(conn, `/api/os/${osId}`);
      if (j?.success && j.os) setOs(j.os);
      else showToast(friendlyApiError(j, "OS não encontrada."), "error");
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao carregar a OS."), "error");
    } finally {
      setOsLoading(false);
    }
  }, [conn, osId, showToast]);

  useEffect(() => { loadOs(); }, [loadOs]);

  useEffect(() => {
    if (!conn) return;
    apiGet(conn, "/api/status-os").then((j) => {
      if (j?.success) setStatusOsOptions((j.items || []).map((s: { codigo: number; descricao: string }) => ({ value: s.codigo, label: s.descricao })));
    }).catch(() => {});
  }, [conn]);

  const eq = useOSEquipamentos({
    conn, editing: !!osId, osId, usuarioCod, classe, showToast,
  });

  // Histórico do equipamento lido pelo QR/busca — casado pelo número de
  // série contra a lista de equipamentos já vinculados a esta OS (regra 1:
  // "carrega... junto com o histórico do equipamento").
  useEffect(() => {
    if (!conn || !params.serie) { setHistorico([]); return; }
    const equip = eq.equipamentos.find((e) => e.numero_de_serie === params.serie);
    if (!equip?.equipamento) { setHistorico([]); return; }
    apiGet(conn, `/api/equipamentos/${equip.equipamento}/historico-os`).then((j) => {
      if (j?.success) setHistorico(j.items || []);
    }).catch(() => {});
  }, [conn, params.serie, eq.equipamentos]);

  const capturarLocalizacao = async (): Promise<{ latitude: number; longitude: number } | null> => {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) {
      showToast("Permissão de localização negada — não é possível registrar check-in/check-out.", "error");
      return null;
    }
    const pos = await Location.getCurrentPositionAsync({});
    return { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
  };

  const handleCheckin = async () => {
    if (!conn || !osId) return;
    setCheckingIn(true);
    try {
      const loc = await capturarLocalizacao();
      if (!loc) return;
      const j = await apiSend(conn, `/api/os/${osId}/checkin`, "POST", {
        latitude: loc.latitude, longitude: loc.longitude,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao registrar check-in."), "error"); return; }
      showToast("Check-in registrado.", "success");
      loadOs();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao registrar check-in."), "error");
    } finally {
      setCheckingIn(false);
    }
  };

  const handleCheckout = async () => {
    if (!conn || !osId) return;
    setCheckingOut(true);
    try {
      const loc = await capturarLocalizacao();
      if (!loc) return;
      const j = await apiSend(conn, `/api/os/${osId}/checkout`, "POST", {
        latitude: loc.latitude, longitude: loc.longitude,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao registrar check-out."), "error"); return; }
      showToast("Check-out registrado.", "success");
      loadOs();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao registrar check-out."), "error");
    } finally {
      setCheckingOut(false);
    }
  };

  const handleFechar = () => {
    if (!conn || !osId) return;
    feedback.showConfirm(
      "Fechar esta O.S.? Use apenas quando o atendimento foi concluído com sucesso.",
      async () => {
        setFechando(true);
        try {
          const j = await apiSend(conn, `/api/os/${osId}/fechar-atendimento`, "POST", {
            classe, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
          });
          if (!j?.success) { showToast(friendlyApiError(j, "Falha ao fechar a O.S."), "error"); return; }
          showToast("O.S. fechada.", "success");
          loadOs();
        } catch (e) {
          showToast(friendlyCatchError(e, "Falha ao fechar a O.S."), "error");
        } finally {
          setFechando(false);
        }
      },
      { title: "Fechar O.S.", confirmText: "Fechar" },
    );
  };

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      const fid = func?.codigo_int ?? func?.codigo;
      setUsuarioCod(fid != null ? parseInt(String(fid), 10) : -2);
      const cl = (s as Record<string, unknown> | null)?.classe;
      setClasse(cl != null ? parseInt(String(cl), 10) : null);
      setBootLoading(false);
    })();
  }, []);

  const statusOsLabel = useMemo(
    () => statusOsOptions.find((o) => o.value === os?.status_os)?.label || os?.status_os_descricao || "",
    [statusOsOptions, os],
  );

  if (bootLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  if (!can("OS_ATENDIMENTO.ABRIR")) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}><LockedView /></SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="os-atendimento-screen">
      <View style={styles.header}>
        <Pressable
          onPress={() => (osId ? router.replace("/os-atendimento") : router.back())}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="os-atendimento-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {osId ? `Atendimento — OS #${osId}` : "Atendimento de Campo"}
        </Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary} testID="os-atendimento-ajuda"
        />
      </View>

      {!osId ? (
        <View style={styles.scannerWrap}>
          {camPerm?.granted && scannerAtivo ? (
            <View style={styles.cameraBox}>
              <CameraView
                style={{ flex: 1 }}
                facing="back"
                barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
                onBarcodeScanned={handleBarcodeScanned}
              />
              <Pressable style={styles.cameraCancelBtn} onPress={() => setScannerAtivo(false)} testID="os-atendimento-cancelar-scan">
                <Text style={styles.cameraCancelText}>Cancelar leitura</Text>
              </Pressable>
            </View>
          ) : (
            <Pressable
              style={styles.qrBtn}
              onPress={async () => {
                if (!camPerm?.granted) {
                  const r = await requestCamPerm();
                  if (!r.granted) { showToast("Permissão de câmera negada.", "error"); return; }
                }
                scanLockRef.current = false;
                setScannerAtivo(true);
              }}
              testID="os-atendimento-ler-qr"
            >
              <Ionicons name="qr-code-outline" size={40} color={colors.brandPrimary} />
              <Text style={styles.qrBtnText}>Ler QR Code do equipamento</Text>
            </Pressable>
          )}

          <Text style={styles.orText}>ou</Text>

          <View style={styles.manualRow}>
            <TextInput
              value={manualSerie}
              onChangeText={setManualSerie}
              placeholder="Número de série do equipamento"
              placeholderTextColor={colors.muted}
              style={styles.manualInput}
              autoCapitalize="characters"
              onSubmitEditing={() => resolveSerie(manualSerie)}
              testID="os-atendimento-serie-manual"
            />
            <Pressable
              onPress={() => resolveSerie(manualSerie)}
              disabled={resolvendo || !manualSerie.trim()}
              style={[styles.buscarBtn, (resolvendo || !manualSerie.trim()) && { opacity: 0.5 }]}
              testID="os-atendimento-buscar-serie"
            >
              {resolvendo ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.buscarBtnText}>Buscar</Text>}
            </Pressable>
          </View>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} testID="os-atendimento-scroll">
          {osLoading || !os ? (
            <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
          ) : (
            <>
              <View style={styles.card}>
                <Text style={styles.clienteNome}>{os.cliente_nome}</Text>
                <Text style={styles.metaText}>{os.situacao_label}{statusOsLabel ? ` · ${statusOsLabel}` : ""}</Text>
                {os.resumo ? <Text style={styles.resumoText}>{os.resumo}</Text> : null}
                {os.descricao_cliente ? <Text style={styles.resumoText}>{os.descricao_cliente}</Text> : null}
              </View>

              {historico.length > 0 ? (
                <View style={styles.card}>
                  <Text style={styles.sectionTitle}>Histórico deste equipamento</Text>
                  {historico.map((h) => (
                    <View key={h.codigo} style={styles.historicoRow}>
                      <Text style={styles.historicoOs}>OS #{h.codigo}</Text>
                      <Text style={styles.historicoMeta}>{h.data || "—"} · {h.situacao}</Text>
                      {h.resumo ? <Text style={styles.historicoResumo} numberOfLines={1}>{h.resumo}</Text> : null}
                    </View>
                  ))}
                </View>
              ) : null}

              {!jaFezCheckin ? (
                <Pressable
                  onPress={handleCheckin}
                  disabled={checkingIn || !isAberta}
                  style={[styles.checkinBtn, (checkingIn || !isAberta) && { opacity: 0.6 }]}
                  testID="os-atendimento-checkin"
                >
                  {checkingIn ? (
                    <>
                      <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                      <Text style={styles.checkinBtnText}>Localizando…</Text>
                    </>
                  ) : (
                    <>
                      <Ionicons name="log-in-outline" size={20} color={colors.onBrandPrimary} />
                      <Text style={styles.checkinBtnText}>Fazer Check-in</Text>
                    </>
                  )}
                </Pressable>
              ) : (
                <View style={styles.card}>
                  <Text style={styles.checkinFeitoText}>Check-in registrado em {os.checkin_em}.</Text>
                  <Text style={styles.sectionTitle}>Equipamentos</Text>
                  {eq.equipamentosLoading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
                  {!eq.equipamentosLoading && eq.equipamentos.length === 0 ? (
                    <Text style={styles.metaText}>Nenhum equipamento vinculado ainda.</Text>
                  ) : null}
                  {eq.equipamentos.map((item) => (
                    <OSEquipamentoCard
                      key={item.codigo}
                      item={item}
                      statusOptions={statusOsOptions}
                      editavel={isAberta}
                      canCancelar={false}
                      saving={eq.savingCodigo === item.codigo}
                      canceling={false}
                      onSalvar={(draft) => eq.handleUpdate(item.codigo, draft)}
                      onCancelar={() => {}}
                    />
                  ))}

                  <Pressable
                    onPress={() => setFormulariosOpen(true)}
                    style={styles.linkBtn}
                    testID="os-atendimento-formularios"
                  >
                    <Ionicons name="document-text-outline" size={16} color={colors.brandPrimary} />
                    <Text style={styles.linkBtnText}>Formulário Dinâmico</Text>
                  </Pressable>

                  {isAberta ? (
                    <Pressable
                      onPress={handleFechar}
                      disabled={fechando}
                      style={[styles.fecharBtn, fechando && { opacity: 0.6 }]}
                      testID="os-atendimento-fechar"
                    >
                      {fechando ? (
                        <>
                          <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                          <Text style={styles.fecharBtnText}>Fechando…</Text>
                        </>
                      ) : (
                        <>
                          <Ionicons name="checkmark-done-outline" size={18} color={colors.onBrandPrimary} />
                          <Text style={styles.fecharBtnText}>Fechar O.S.</Text>
                        </>
                      )}
                    </Pressable>
                  ) : null}

                  {!jaFezCheckout ? (
                    <Pressable
                      onPress={handleCheckout}
                      disabled={checkingOut}
                      style={[styles.checkoutBtn, checkingOut && { opacity: 0.6 }]}
                      testID="os-atendimento-checkout"
                    >
                      {checkingOut ? (
                        <>
                          <ActivityIndicator color={colors.brandPrimary} size="small" />
                          <Text style={styles.checkoutBtnText}>Localizando…</Text>
                        </>
                      ) : (
                        <>
                          <Ionicons name="log-out-outline" size={18} color={colors.brandPrimary} />
                          <Text style={styles.checkoutBtnText}>Fazer Check-out</Text>
                        </>
                      )}
                    </Pressable>
                  ) : (
                    <Text style={styles.checkoutFeitoText}>Check-out registrado em {os.checkout_em}.</Text>
                  )}
                </View>
              )}
            </>
          )}
        </ScrollView>
      )}

      <ScreenToast toast={toast} testID="os-atendimento-toast" />
      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Atendimento de Campo" itens={AJUDA_ITENS} />
      {osId ? (
        <LayoutPreenchimentoModal
          visible={formulariosOpen}
          onClose={() => setFormulariosOpen(false)}
          conn={conn}
          entidade={LAYOUT_ENTIDADE_OS}
          codentidade={osId}
          usuarioCod={usuarioCod}
          title="Formulários (Layouts) da O.S."
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: spacing.xl },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  scroll: { padding: spacing.lg },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.md,
  },
  clienteNome: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  metaText: { fontSize: 13, color: colors.muted, marginTop: 2 },
  resumoText: { fontSize: 13, color: colors.onSurface, marginTop: 6 },
  sectionTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface, marginBottom: spacing.sm, textTransform: "uppercase", letterSpacing: 0.4 },
  historicoRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: spacing.sm },
  historicoOs: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  historicoMeta: { fontSize: 11, color: colors.muted },
  historicoResumo: { fontSize: 12, color: colors.onSurface, marginTop: 2 },
  // Scanner / busca manual.
  scannerWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md },
  cameraBox: { width: "100%", aspectRatio: 1, maxWidth: 360, borderRadius: radius.md, overflow: "hidden", backgroundColor: "#000" },
  cameraCancelBtn: { position: "absolute", bottom: spacing.md, alignSelf: "center", backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.md },
  cameraCancelText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  qrBtn: {
    width: "100%", maxWidth: 360, aspectRatio: 1.6, borderRadius: radius.md, borderWidth: 2, borderColor: colors.brandPrimary, borderStyle: "dashed",
    alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary,
  },
  qrBtnText: { fontSize: 14, fontWeight: "600", color: colors.brandPrimary, textAlign: "center", paddingHorizontal: spacing.lg },
  orText: { fontSize: 12, color: colors.muted },
  manualRow: { flexDirection: "row", gap: spacing.sm, width: "100%", maxWidth: 360 },
  manualInput: {
    flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: 14,
  },
  buscarBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.md, alignItems: "center", justifyContent: "center", minWidth: 84 },
  buscarBtnText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "600" },
  // Check-in/check-out/fechar.
  checkinBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 16, marginHorizontal: spacing.lg,
  },
  checkinBtnText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "700" },
  checkoutBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, marginTop: spacing.sm,
  },
  checkoutBtnText: { color: colors.brandPrimary, fontSize: 14, fontWeight: "700" },
  checkoutFeitoText: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, textAlign: "center" },
  checkinFeitoText: { fontSize: 12, color: colors.muted, marginBottom: spacing.sm },
  fecharBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.success, borderRadius: radius.md, paddingVertical: 12, marginTop: spacing.md,
  },
  fecharBtnText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "700" },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginTop: spacing.md },
  linkBtnText: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
});
