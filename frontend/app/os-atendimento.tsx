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
  ActivityIndicator, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View,
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
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import {
  cacheOsParaOffline, getOsCacheada, listarTodasCacheadas, enfileirarMutacao,
  listarFilaPendente, removerDaFila,
  MutacaoPendente,
} from "@/src/utils/storage/offlineAtendimento";
import { syncFilaOS } from "@/src/utils/offlineSync/atendimentoSync";

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
  // Usados pra decidir se quem está atuando precisa "emprestar" a
  // credencial do técnico titular (regra 11) — ver `needsElevation`.
  tecnico_responsavel: number | null;
  tecnico_responsavel_nome: string;
  // Token opaco de concorrência otimista (ROWVERSION em hex) — ver
  // "Sincronização Offline" em AssistenciaTecnicaCampo.md. Nunca
  // interpretado no frontend, só reenviado como `versao_esperada`.
  versao_atendimento?: string | null;
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
  {
    titulo: "Credencial do técnico",
    texto: "Se você não é o técnico responsável por esta OS (ex.: é o auxiliar dele, e o celular do técnico ficou sem bateria), o sistema pede o usuário e a senha do técnico titular antes de gravar qualquer coisa. Digitado uma vez, vale pro resto da visita.",
    icon: { lib: "ion", name: "key-outline" },
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
      if (e instanceof TypeError) {
        // Sem conexão — procura o número de série em toda OS já pré-
        // carregada localmente (ver AssistenciaTecnicaCampo.md, "Sincronização
        // Offline" — pré-carga automática feita por os-lista.tsx).
        const todas = await listarTodasCacheadas();
        const achado = todas.find((c) => c.bundle.equipamentos.some((it) => it.numero_de_serie === s));
        if (achado) {
          showToast("Sem conexão — abrindo dados salvos localmente.", "info");
          router.replace({ pathname: "/os-atendimento", params: { os: String(achado.codigo), serie: s } });
          return;
        }
        showToast("Sem conexão e este equipamento ainda não foi salvo localmente.", "error");
        return;
      }
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

  // ---------- Sincronização Offline (ver AssistenciaTecnicaCampo.md) ----------
  const [offline, setOffline] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [filaPendente, setFilaPendente] = useState<MutacaoPendente[]>([]);
  const [sincronizando, setSincronizando] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [conflito, setConflito] = useState<{ id: string; message: string } | null>(null);
  const osRef = useRef<OSAtendimentoData | null>(null);

  const refreshFila = useCallback(async () => {
    if (!osId) { setFilaPendente([]); return; }
    setFilaPendente(await listarFilaPendente(osId));
  }, [osId]);
  useEffect(() => { refreshFila(); }, [refreshFila]);

  const isAberta = os?.situacao === "A";
  const jaFezCheckin = !!os?.checkin_em;
  const jaFezCheckout = !!os?.checkout_em;

  // Auxiliar edita a OS em nome do técnico titular (regra 11,
  // AssistenciaTecnicaCampo.md — celular do técnico sem bateria). Quem
  // está logado precisa "emprestar" a credencial do técnico atribuído a
  // esta OS antes de gravar qualquer coisa, A MENOS que já seja o próprio
  // técnico, ou tenha `OS_COMP.VER_TODAS` (gestor/supervisão — edita
  // livre, decisão explícita do usuário). Sem técnico atribuído à OS, não
  // há "titular" pra proteger — ninguém precisa elevar.
  const [elevado, setElevado] = useState(false);
  const [authSlideOpen, setAuthSlideOpen] = useState(false);
  const needsElevation = !!(
    os?.tecnico_responsavel != null
    && os.tecnico_responsavel !== usuarioCod
    && !can("OS_COMP.VER_TODAS")
  );
  // Uma vez elevado, toda gravação passa a ser atribuída ao TÉCNICO (não
  // a quem está com o celular na mão) — "em nome dele", não só "com a
  // permissão dele".
  const effectiveUsuarioCod = (needsElevation && elevado && os?.tecnico_responsavel != null)
    ? os.tecnico_responsavel
    : usuarioCod;
  // Rastreabilidade — quem estava FISICAMENTE logado, só pra enriquecer o
  // log de auditoria (nunca usado em regra de negócio). `undefined` no
  // caso comum (sem elevação), então os endpoints nem recebem o campo.
  const viaAuxiliar = (needsElevation && elevado) ? usuarioCod : undefined;
  // Reseta a elevação ao trocar de OS (não deve "vazar" de uma visita pra
  // outra) — cada `?os=` novo é uma tela nova pro React, mas o componente
  // é o mesmo (navegação via router.replace), então o estado sobrevive
  // sem isto.
  useEffect(() => { setElevado(false); }, [osId]);

  const loadOs = useCallback(async () => {
    if (!conn || !osId) return;
    setOsLoading(true);
    try {
      // /api/os-completo (não só /api/os) — precisa de tecnico_responsavel
      // pra decidir se quem está atuando precisa da elevação (regra 11).
      const j = await apiGet(conn, `/api/os-completo/${osId}`);
      if (j?.success && j.os) {
        setOs(j.os);
        setOffline(false);
        setCachedAt(null);
      } else showToast(friendlyApiError(j, "OS não encontrada."), "error");
    } catch (e) {
      if (e instanceof TypeError) {
        const cache = await getOsCacheada(osId);
        if (cache) {
          setOs(cache.os as unknown as OSAtendimentoData);
          setOffline(true);
          setCachedAt(cache.cachedAt);
          showToast("Sem conexão — exibindo dados salvos localmente.", "info");
          return;
        }
        showToast("Sem conexão e esta OS ainda não foi salva localmente.", "error");
        return;
      }
      showToast(friendlyCatchError(e, "Falha ao carregar a OS."), "error");
    } finally {
      setOsLoading(false);
    }
  }, [conn, osId, showToast]);

  useEffect(() => { loadOs(); }, [loadOs]);
  useEffect(() => { osRef.current = os; }, [os]);

  useEffect(() => {
    if (!conn) return;
    apiGet(conn, "/api/status-os").then((j) => {
      if (j?.success) setStatusOsOptions((j.items || []).map((s: { codigo: number; descricao: string }) => ({ value: s.codigo, label: s.descricao })));
    }).catch(() => {});
  }, [conn]);

  const eq = useOSEquipamentos({
    conn, editing: !!osId, osId, usuarioCod: effectiveUsuarioCod, classe, showToast, viaAuxiliar,
    onOfflineFallback: (itemCodigo, draft) => {
      if (!osId) return;
      enfileirarMutacao({
        tipo: "equipamento", osId, itemCodigo,
        payload: { ...draft, usuario_alteracao: effectiveUsuarioCod, classe, plataforma: Platform.OS, via_auxiliar: viaAuxiliar },
      });
      showToast("Sem conexão — alteração salva localmente, sincroniza depois.", "info");
      refreshFila();
    },
  });

  // Recarrega o cache local desta OS sempre que os dados online mais
  // recentes chegam (após loadOs/sincronização bem-sucedidos) — reforça a
  // pré-carga automática já feita por os-lista.tsx e garante que
  // `versaoAtendimento` usado pela sincronização é sempre o mais atual já
  // confirmado online. Nunca grava por cima de dados que já estão em modo
  // offline (o `cache` já É a fonte, regravar destruiria o `cachedAt` real).
  useEffect(() => {
    if (!osId || !os || offline || eq.equipamentosLoading) return;
    cacheOsParaOffline(osId, {
      os: os as unknown as Record<string, unknown>,
      equipamentos: eq.equipamentos,
      historico: [],
      statusOsOptions,
      versaoAtendimento: os.versao_atendimento ?? null,
    });
  }, [osId, os, offline, eq.equipamentos, eq.equipamentosLoading, statusOsOptions]);

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
    if (needsElevation && !elevado) { setAuthSlideOpen(true); return; }
    setCheckingIn(true);
    let payload: Record<string, unknown> | null = null;
    try {
      const loc = await capturarLocalizacao();
      if (!loc) return;
      payload = {
        latitude: loc.latitude, longitude: loc.longitude,
        usuario_alteracao: effectiveUsuarioCod, classe, plataforma: Platform.OS, via_auxiliar: viaAuxiliar,
      };
      const j = await apiSend(conn, `/api/os/${osId}/checkin`, "POST", payload);
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao registrar check-in."), "error"); return; }
      showToast("Check-in registrado.", "success");
      loadOs();
    } catch (e) {
      if (e instanceof TypeError && payload) {
        await enfileirarMutacao({ tipo: "checkin", osId, payload });
        setOs((prev) => (prev ? { ...prev, checkin_em: new Date().toISOString() } : prev));
        showToast("Sem conexão — check-in salvo localmente, sincroniza depois.", "info");
        refreshFila();
        return;
      }
      showToast(friendlyCatchError(e, "Falha ao registrar check-in."), "error");
    } finally {
      setCheckingIn(false);
    }
  };

  const handleCheckout = async () => {
    if (!conn || !osId) return;
    if (needsElevation && !elevado) { setAuthSlideOpen(true); return; }
    setCheckingOut(true);
    let payload: Record<string, unknown> | null = null;
    try {
      const loc = await capturarLocalizacao();
      if (!loc) return;
      payload = {
        latitude: loc.latitude, longitude: loc.longitude,
        usuario_alteracao: effectiveUsuarioCod, classe, plataforma: Platform.OS, via_auxiliar: viaAuxiliar,
      };
      const j = await apiSend(conn, `/api/os/${osId}/checkout`, "POST", payload);
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao registrar check-out."), "error"); return; }
      showToast("Check-out registrado.", "success");
      loadOs();
    } catch (e) {
      if (e instanceof TypeError && payload) {
        await enfileirarMutacao({ tipo: "checkout", osId, payload });
        setOs((prev) => (prev ? { ...prev, checkout_em: new Date().toISOString() } : prev));
        showToast("Sem conexão — check-out salvo localmente, sincroniza depois.", "info");
        refreshFila();
        return;
      }
      showToast(friendlyCatchError(e, "Falha ao registrar check-out."), "error");
    } finally {
      setCheckingOut(false);
    }
  };

  const handleFechar = () => {
    if (!conn || !osId) return;
    if (needsElevation && !elevado) { setAuthSlideOpen(true); return; }
    feedback.showConfirm(
      "Fechar esta O.S.? Use apenas quando o atendimento foi concluído com sucesso.",
      async () => {
        setFechando(true);
        const payload = {
          classe, usuario_alteracao: effectiveUsuarioCod, plataforma: Platform.OS, via_auxiliar: viaAuxiliar,
        };
        try {
          const j = await apiSend(conn, `/api/os/${osId}/fechar-atendimento`, "POST", payload);
          if (!j?.success) { showToast(friendlyApiError(j, "Falha ao fechar a O.S."), "error"); return; }
          showToast("O.S. fechada.", "success");
          loadOs();
        } catch (e) {
          if (e instanceof TypeError) {
            await enfileirarMutacao({ tipo: "fechar", osId, payload });
            setOs((prev) => (prev ? { ...prev, situacao: "F", situacao_label: "Fechada" } : prev));
            showToast("Sem conexão — fechamento salvo localmente, sincroniza depois.", "info");
            refreshFila();
            return;
          }
          showToast(friendlyCatchError(e, "Falha ao fechar a O.S."), "error");
        } finally {
          setFechando(false);
        }
      },
      { title: "Fechar O.S.", confirmText: "Fechar" },
    );
  };

  // Motor de sincronização — extraído pra `atendimentoSync.ts` (reaproveitado
  // também por os-lista.tsx, ver AssistenciaTecnicaCampo.md "Sincronização
  // Offline"). Usa `osRef` (não `os` direto) pra manter a identidade do
  // callback estável entre renders — senão o efeito de disparo automático
  // (mount/troca de OS) reexecutaria a cada `loadOs()` que a própria
  // sincronização provoca.
  const sincronizarFila = useCallback(async () => {
    if (!conn || !osId) return;
    setSincronizando(true);
    const versaoInicial = osRef.current?.versao_atendimento ?? (await getOsCacheada(osId))?.versaoAtendimento ?? null;
    const resultado = await syncFilaOS(conn, osId, versaoInicial);
    setSincronizando(false);
    if (resultado.conflito) setConflito(resultado.conflito);
    if (resultado.algumSucesso || resultado.conflito) { loadOs(); eq.loadEquipamentos(); }
    refreshFila();
  }, [conn, osId, loadOs, eq.loadEquipamentos, refreshFila]);

  // Dispara automaticamente ao abrir a tela com uma OS (item "a" da
  // decisão de detecção de rede) — não monitora a conexão, só tenta.
  useEffect(() => { if (osId) sincronizarFila(); }, [osId, sincronizarFila]);

  const resolverConflito = async () => {
    if (conflito) await removerDaFila(conflito.id);
    setConflito(null);
    await loadOs();
    await eq.loadEquipamentos();
    refreshFila();
  };

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await sincronizarFila();
    await loadOs();
    await eq.loadEquipamentos();
    setRefreshing(false);
  }, [sincronizarFila, loadOs, eq.loadEquipamentos]);

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
        <ScrollView
          contentContainerStyle={styles.scroll}
          testID="os-atendimento-scroll"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.brandPrimary]} tintColor={colors.brandPrimary} />}
        >
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

              {offline ? (
                <View style={styles.offlineBanner} testID="os-atendimento-offline-banner">
                  <Ionicons name="cloud-offline-outline" size={14} color={colors.warning} />
                  <Text style={styles.offlineBannerText}>
                    Sem conexão — exibindo dados salvos {cachedAt ? `em ${new Date(cachedAt).toLocaleString("pt-BR")}` : "localmente"}. Vai sincronizar quando a conexão voltar.
                  </Text>
                </View>
              ) : null}

              {conflito ? (
                <View style={styles.conflitoBanner} testID="os-atendimento-conflito-banner">
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Ionicons name="warning-outline" size={16} color={colors.error} />
                    <Text style={styles.conflitoBannerText}>{conflito.message}</Text>
                  </View>
                  <Pressable onPress={resolverConflito} style={styles.conflitoBtn} testID="os-atendimento-conflito-recarregar">
                    <Text style={styles.conflitoBtnText}>Recarregar dados atuais</Text>
                  </Pressable>
                </View>
              ) : null}

              {!conflito && filaPendente.filter((m) => !m.erro).length > 0 ? (
                <View style={styles.filaBanner} testID="os-atendimento-fila-banner">
                  <Ionicons name="sync-outline" size={14} color={colors.brandPrimary} />
                  <Text style={styles.filaBannerText}>
                    {filaPendente.filter((m) => !m.erro).length} {filaPendente.filter((m) => !m.erro).length === 1 ? "alteração pendente" : "alterações pendentes"} de sincronização.
                  </Text>
                  <Pressable onPress={sincronizarFila} disabled={sincronizando} style={styles.filaBtn} testID="os-atendimento-sincronizar">
                    {sincronizando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.filaBtnText}>Sincronizar</Text>}
                  </Pressable>
                </View>
              ) : null}

              {/* Mutações que falharam por regra de negócio (não conflito,
                  não rede) — não bloqueiam o resto da fila, mas ficam
                  presas até o técnico revisar e descartar manualmente
                  (achado de revisão Gauntlet retroativa, ver
                  AssistenciaTecnicaCampo.md "Sincronização Offline"). */}
              {filaPendente.filter((m) => m.erro).map((m) => (
                <View key={m.id} style={styles.filaErroRow} testID={`os-atendimento-fila-erro-${m.id}`}>
                  <Ionicons name="alert-circle-outline" size={14} color={colors.error} />
                  <Text style={styles.filaErroText} numberOfLines={3}>{m.erro}</Text>
                  <Pressable
                    onPress={async () => { await removerDaFila(m.id); refreshFila(); }}
                    style={styles.filaErroBtn}
                    testID={`os-atendimento-descartar-${m.id}`}
                  >
                    <Text style={styles.filaErroBtnText}>Descartar</Text>
                  </Pressable>
                </View>
              ))}

              {needsElevation && elevado ? (
                <View style={styles.elevadoBanner} testID="os-atendimento-elevado-banner">
                  <Ionicons name="key-outline" size={14} color={colors.brandPrimary} />
                  <Text style={styles.elevadoBannerText}>
                    Atuando em nome de {os.tecnico_responsavel_nome || "técnico responsável"} (credencial autorizada)
                  </Text>
                </View>
              ) : null}

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
                      onSalvar={(draft) => {
                        if (needsElevation && !elevado) { setAuthSlideOpen(true); return; }
                        eq.handleUpdate(item.codigo, draft);
                      }}
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
      <AuthorizationSlide
        visible={authSlideOpen}
        conn={conn}
        title="Credencial do técnico"
        message={`Esta OS está atribuída a ${os?.tecnico_responsavel_nome || "outro técnico"}. Peça a ele para informar o usuário e a senha para continuar em nome dele.`}
        codigoEsperado={os?.tecnico_responsavel ?? undefined}
        onClose={() => setAuthSlideOpen(false)}
        onAuthorized={() => { setElevado(true); setAuthSlideOpen(false); }}
      />
      {osId ? (
        <LayoutPreenchimentoModal
          visible={formulariosOpen}
          onClose={() => setFormulariosOpen(false)}
          conn={conn}
          entidade={LAYOUT_ENTIDADE_OS}
          codentidade={osId}
          usuarioCod={usuarioCod}
          title="Formulários (Layouts) da O.S."
          onSalvarOffline={(payload) => {
            enfileirarMutacao({ tipo: "formulario", osId, payload });
            showToast("Sem conexão — preenchimento salvo localmente, sincroniza depois.", "info");
            refreshFila();
          }}
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
  elevadoBanner: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary + "18", borderWidth: 1, borderColor: colors.brandPrimary,
    borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.md,
  },
  elevadoBannerText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", flex: 1 },
  offlineBanner: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.warning + "18", borderWidth: 1, borderColor: colors.warning,
    borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.md,
  },
  offlineBannerText: { fontSize: 12, color: colors.warning, fontWeight: "600", flex: 1 },
  conflitoBanner: {
    gap: spacing.sm,
    backgroundColor: colors.error + "18", borderWidth: 1, borderColor: colors.error,
    borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md,
  },
  conflitoBannerText: { fontSize: 12, color: colors.error, fontWeight: "600", flex: 1 },
  conflitoBtn: { backgroundColor: colors.error, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" },
  conflitoBtnText: { color: "#fff", fontSize: 13, fontWeight: "700" },
  filaBanner: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary + "12", borderWidth: 1, borderColor: colors.brandPrimary,
    borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.md,
  },
  filaBannerText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", flex: 1 },
  filaBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 6, minWidth: 84, alignItems: "center" },
  filaBtnText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "700" },
  filaErroRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.error + "12", borderWidth: 1, borderColor: colors.error,
    borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.sm,
  },
  filaErroText: { fontSize: 11, color: colors.error, flex: 1 },
  filaErroBtn: { borderWidth: 1, borderColor: colors.error, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 6 },
  filaErroBtnText: { color: colors.error, fontSize: 11, fontWeight: "700" },
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
