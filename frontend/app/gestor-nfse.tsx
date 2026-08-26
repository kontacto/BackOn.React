// Gestor NFSe — Sefin Nacional/DPS, migração de `Geral\FrmManNSeSefin.frm`
// (ações "Selecionar"/"Recuperar Informações"/"Enviar por E-mail" +
// "Baixar DANFE", 2026-08-20) — completa a Fase 3 do pacote de emissão de
// NFS-e (já implementada em `alterar-comanda.tsx` > "Emitir NFS-e"). NÃO é
// o caminho antigo por RPS municipal (Geral\FrmManNSe.frm, Ginfes/ABRASF
// por prefeitura, não implementado — decisão explícita do usuário
// 2026-08-20, ver PENDENCIAS.md > "Gestor NFSe").
//
// Fonte real dos dados: tabela `dps` (não `n_fiscal` sozinha) — ver
// `backend/services/gestor_nfse_service.py` pro racional completo.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import WebDateField from "@/src/components/WebDateField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { useClienteSearchModal } from "@/src/hooks/useClienteSearchModal";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";

function brDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

type NfseItem = {
  codigo: number;
  num_dps: number | null;
  serie_dps: string | null;
  data_dps: string | null;
  valor_total: number | null;
  STATUS: string | null;
  situacao: string | null;
  chave_acesso_dps: string | null;
  chave_acesso_nfse: string | null;
  comanda: number;
  cliente_codigo: number | null;
  cliente_nome: string | null;
};
type ResultadoLinha = { codigo: number; success: boolean; message?: string };

const GESTOR_NFSE_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Buscar e Filtrar",
    texto: "Filtra por período de emissão da DPS, número da comanda ou código do cliente.",
    icon: { lib: "ion", name: "filter-outline" },
  },
  {
    titulo: "Selecionar linhas",
    texto: "Marque uma ou mais NFS-e na lista para liberar \"Recuperar Informações\" na barra que aparece acima da lista.",
    icon: { lib: "ion", name: "checkbox-outline" },
  },
  {
    titulo: "Recuperar Informações",
    texto: "Consulta a situação atual junto ao Ambiente de Dados Nacional (ADN/Sefin Nacional) e atualiza o status guardado no sistema — útil pra conferir se a nota realmente foi autorizada.",
    icon: { lib: "ion", name: "search-outline" },
  },
  {
    titulo: "Baixar DANFE",
    texto: "Baixa o PDF oficial da NFS-e direto do Ambiente de Dados Nacional (ADN) — só disponível para notas já com chave de acesso (transmitidas).",
    icon: { lib: "ion", name: "download-outline" },
  },
  {
    titulo: "Enviar por E-mail",
    texto: "Manda o DANFE em PDF por e-mail para o cliente da comanda, usando o e-mail cadastrado — bloqueia se o cliente não tiver e-mail.",
    icon: { lib: "ion", name: "mail-outline" },
  },
  {
    titulo: "Emitir uma NFS-e nova",
    texto: "Esta tela não emite — vá em Gestor de Comandas, abra a comanda faturada e use \"Emitir NFS-e\".",
    icon: { lib: "ion", name: "information-circle-outline" },
  },
];

export default function GestorNfseScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gestor NFSe está disponível apenas no web." testID="gestor-nfse-web-only" />;
  }

  const canAbrir = can("GESTOR_NFSE.ABRIR") || isMaster;
  const canConsultar = can("GESTOR_NFSE.CONSULTAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(false);
  const [consultando, setConsultando] = useState(false);

  const [dataDe, setDataDe] = useState<string | null>(null);
  const [dataAte, setDataAte] = useState<string | null>(null);
  const [comandaNum, setComandaNum] = useState("");
  const [clienteCodigo, setClienteCodigo] = useState("");
  const clienteSearch = useClienteSearchModal(conn);

  const [itens, setItens] = useState<NfseItem[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [ajudaVisivel, setAjudaVisivel] = useState(false);
  const [resultadoLote, setResultadoLote] = useState<{ titulo: string; linhas: ResultadoLinha[] } | null>(null);
  const [baixandoDanfe, setBaixandoDanfe] = useState<Set<number>>(new Set());
  const [enviandoEmail, setEnviandoEmail] = useState(false);

  const apiUrl = useCallback((path: string) => `${(conn?.api || "").replace(/\/+$/, "")}${path}`, [conn]);
  const int_ = (s: string): number | undefined => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || undefined : undefined);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        data_de: dataDe || undefined, data_ate: dataAte || undefined,
        comanda: int_(comandaNum), cliente: int_(clienteCodigo),
        classe, master: isMaster,
      };
      const r = await fetch(apiUrl("/api/gestor-nfse"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        setItens(j.itens || []);
        setSelecionados(new Set());
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível consultar as NFS-e."));
        setItens([]);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, dataDe, dataAte, comandaNum, clienteCodigo, classe, isMaster, fb, apiUrl]);

  useEffect(() => {
    if (conn) buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const toggleSelecionado = (codigo: number) => {
    setSelecionados((cur) => {
      const next = new Set(cur);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };
  const todosSelecionados = itens.length > 0 && selecionados.size === itens.length;
  const alternarTodos = () => {
    setSelecionados(todosSelecionados ? new Set() : new Set(itens.map((it) => it.codigo)));
  };

  const consultarSelecionadas = async () => {
    if (!conn || selecionados.size === 0) return;
    setConsultando(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco, codigos: Array.from(selecionados),
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(apiUrl("/api/gestor-nfse/consultar"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (Array.isArray(j?.resultados)) {
        setResultadoLote({ titulo: "Recuperar Informações", linhas: j.resultados });
      }
      if (j?.success) {
        fb.showSuccess("Consulta concluída.", undefined, 5000);
        buscar();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível concluir a consulta."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setConsultando(false);
    }
  };

  // Baixar DANFE (PDF) — busca do ADN (com cache em `dps.PDF_DANFE_NFSE`)
  // e dispara o download no navegador, mesmo padrão já usado pra baixar a
  // remessa CNAB em `geracao-boletos.tsx` (Blob + <a download>).
  const baixarDanfe = async (it: NfseItem) => {
    if (!conn) return;
    setBaixandoDanfe((cur) => new Set(cur).add(it.codigo));
    try {
      const r = await fetch(apiUrl("/api/gestor-nfse/danfe"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, codigo: it.codigo,
          usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
        }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showWarning(friendlyApiError(j, "Não foi possível baixar o DANFE.")); return; }
      const binario = atob(j.pdf_base64);
      const bytes = new Uint8Array(binario.length);
      for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `DANFE_NFSe_${it.num_dps || it.codigo}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setBaixandoDanfe((cur) => { const next = new Set(cur); next.delete(it.codigo); return next; });
    }
  };

  // Enviar por e-mail — réplica de "Command4_Click" do legado, mas o DANFE
  // é buscado fresco do ADN em vez de um cache local em disco que este
  // backend nunca teve (ver docstring de gestor_nfse_service.py).
  const enviarEmailSelecionadas = async () => {
    if (!conn || selecionados.size === 0) return;
    setEnviandoEmail(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco, codigos: Array.from(selecionados),
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(apiUrl("/api/gestor-nfse/enviar-email"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (Array.isArray(j?.resultados)) {
        setResultadoLote({ titulo: "Enviar por E-mail", linhas: j.resultados });
      }
      if (j?.success) {
        fb.showSuccess("E-mail(s) enviado(s) com sucesso.", undefined, 5000);
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível enviar todos os e-mails."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setEnviandoEmail(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Gestor NFSe." testID="gestor-nfse-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="gestor-nfse-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Gestor NFSe</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="gestor-nfse-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="gestor-nfse-filtros">
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Emissão DPS, de</Text>
                  <WebDateField
                    value={dataDe}
                    onChange={(v) => { setDataDe(v || null); if (v) setDataAte(v); }}
                    testID="gestor-nfse-data-ini"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                  <WebDateField value={dataAte} onChange={setDataAte} testID="gestor-nfse-data-fim" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Comanda</Text>
                  <TextInput value={comandaNum} onChangeText={(v) => setComandaNum(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-nfse-comanda" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cód. Cliente</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                    <TextInput
                      value={clienteCodigo} onChangeText={(v) => setClienteCodigo(v.replace(/\D/g, ""))}
                      style={[styles.input, { flex: 1, minWidth: 0 }]} keyboardType="number-pad" testID="gestor-nfse-cliente"
                    />
                    <IconButtonWithTooltip
                      icon="search-outline" label="Buscar Cliente" onPress={clienteSearch.openModal}
                      size={18} color={colors.brandPrimary} testID="gestor-nfse-cliente-buscar"
                    />
                  </View>
                </View>
              </View>
              <View style={styles.modalActionsRow}>
                <Pressable onPress={buscar} disabled={loading} style={styles.primaryBtn} testID="gestor-nfse-buscar">
                  {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Consultar</Text>}
                </Pressable>
              </View>
            </AccordionSection>
          </View>

          {selecionados.size > 0 ? (
            <View style={styles.bulkBar} testID="gestor-nfse-bulk-bar">
              <Text style={styles.bulkBarLabel}>{selecionados.size} selecionada{selecionados.size === 1 ? "" : "s"}</Text>
              {canConsultar ? (
                <Pressable onPress={consultarSelecionadas} disabled={consultando} style={styles.bulkBtn} testID="gestor-nfse-bulk-consultar">
                  {consultando ? <ActivityIndicator color="#fff" size="small" /> : (
                    <><Ionicons name="search-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Recuperar Informações</Text></>
                  )}
                </Pressable>
              ) : null}
              {canConsultar ? (
                <Pressable onPress={enviarEmailSelecionadas} disabled={enviandoEmail} style={styles.bulkBtn} testID="gestor-nfse-bulk-email">
                  {enviandoEmail ? <ActivityIndicator color="#fff" size="small" /> : (
                    <><Ionicons name="mail-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Enviar por E-mail</Text></>
                  )}
                </Pressable>
              ) : null}
            </View>
          ) : null}

          <View style={styles.card}>
            {loading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : itens.length === 0 ? (
              <Text style={styles.hint}>Nenhuma NFS-e encontrada para os filtros selecionados.</Text>
            ) : (
              <>
                <Pressable onPress={alternarTodos} style={styles.selectAllRow} testID="gestor-nfse-selecionar-todos">
                  <Ionicons name={todosSelecionados ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Selecionar todas ({itens.length})</Text>
                </Pressable>
                {itens.map((it) => (
                  <View key={it.codigo} style={styles.itemRow} testID={`gestor-nfse-item-${it.codigo}`}>
                    <Pressable onPress={() => toggleSelecionado(it.codigo)} hitSlop={8} testID={`gestor-nfse-check-${it.codigo}`}>
                      <Ionicons name={selecionados.has(it.codigo) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    </Pressable>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText}>
                        CMD #{it.comanda}
                        {" · "}{brDate(it.data_dps)} · {it.cliente_nome || "-"} · <Text style={{ fontWeight: "700" }}>{formatBRL(it.valor_total || 0)}</Text>
                      </Text>
                      <Text style={styles.hint}>
                        <Text style={{ color: it.STATUS === "Transmitida" ? colors.success : colors.warning, fontWeight: "600" }}>
                          {it.STATUS || "Sem status"}
                        </Text>
                        {it.num_dps ? ` · DPS ${it.num_dps}${it.serie_dps ? "/" + it.serie_dps : ""}` : ""}
                        {it.chave_acesso_nfse ? ` · Chave ${it.chave_acesso_nfse}` : ""}
                      </Text>
                    </View>
                    {it.chave_acesso_nfse ? (
                      baixandoDanfe.has(it.codigo) ? (
                        <ActivityIndicator color={colors.brandPrimary} size="small" />
                      ) : (
                        <IconButtonWithTooltip
                          icon="download-outline" label="Baixar DANFE" onPress={() => baixarDanfe(it)}
                          size={20} color={colors.brandPrimary} testID={`gestor-nfse-danfe-${it.codigo}`}
                        />
                      )
                    ) : null}
                  </View>
                ))}
              </>
            )}
          </View>
        </View>
      </ScrollView>

      <AppModal visible={!!resultadoLote} transparent animationType="fade" onRequestClose={() => setResultadoLote(null)}>
        <Pressable style={styles.modalBg} onPress={() => setResultadoLote(null)}>
          <Pressable style={[styles.modalCard, { maxHeight: "80%" }]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{resultadoLote?.titulo}</Text>
              <Pressable onPress={() => setResultadoLote(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 380 }}>
              {(resultadoLote?.linhas || []).map((l, idx) => (
                <View key={idx} style={styles.resultadoLinha}>
                  <Ionicons name={l.success ? "checkmark-circle" : "close-circle"} size={18} color={l.success ? colors.success : colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>NFS-e #{l.codigo}</Text>
                    <Text style={styles.hint}>{l.message || (l.success ? "Concluído." : "")}</Text>
                  </View>
                </View>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Gestor NFSe" itens={GESTOR_NFSE_AJUDA_ITENS} />

      <ClientSearchModal
        visible={clienteSearch.open}
        onClose={clienteSearch.closeModal}
        term={clienteSearch.term}
        setTerm={clienteSearch.setTerm}
        loading={clienteSearch.loading}
        results={clienteSearch.results}
        onPick={(c) => { setClienteCodigo(String(c.codigo)); clienteSearch.closeModal(); }}
        onCreate={clienteSearch.closeModal}
      />
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
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colTiny: { width: 100 },
  colNarrow: { width: 170 },

  checkLabel: { fontSize: 13, color: colors.onSurface },
  selectAllRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: 4 },

  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  bulkBar: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm, backgroundColor: colors.surfaceSecondary },
  bulkBarLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  bulkBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  bulkBtnText: { color: "#fff", fontWeight: "600", fontSize: 12 },

  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowText: { fontSize: 13, color: colors.onSurface },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 420, borderWidth: 1, borderColor: colors.border },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  resultadoLinha: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
});
