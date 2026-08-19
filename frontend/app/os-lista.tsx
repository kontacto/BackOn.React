// Lista de O.S. da O.S. Completa — mesma relação de `pedido-lista.tsx` com
// `pedido-geral.tsx`: a O.S. Mobile continua com sua própria tela
// (`app/os.tsx`), esta é exclusiva da O.S. Completa. Reaproveita o mesmo
// endpoint `POST /api/os` (já suporta busca/situação/período/técnico/
// auxiliar) que `os.tsx` usa.
//
// 2026-08-14, user-directed: passou a funcionar TAMBÉM no mobile (não mais
// `Platform.OS !== "web"` → `LockedView`), e o toque numa linha decide
// entre abrir a O.S. Completa (`os-geral.tsx`, web/desktop) ou a tela de
// Atendimento (`os-atendimento.tsx`, mobile/celular) conforme a plataforma
// — aplicando a permissão respectiva de cada uma (`OS_COMP.ABRIR`/
// `OS_ATENDIMENTO.ABRIR`). Ganhou também: filtros de Técnico/Auxiliar,
// restrição de visibilidade (`OS_COMP.VER_TODAS` — sem essa permissão, só
// enxerga O.S. onde é técnico ou auxiliar, resolvido no backend), e cada
// linha mostra o máximo de informação possível (técnico, auxiliar,
// check-in, check-out, próxima agenda) sem precisar abrir a OS — com link
// pra ver o histórico dos equipamentos vinculados.
//
// **Correção 2026-08-15**: nesse mesmo dia esta tela chegou a se
// autodenominar "a Lista de Atendimento" da Assistência Técnica — decisão
// revertida a pedido explícito do usuário. Essa função (calendário +
// entrada inicial do app do técnico, regras 6/7/10 de
// AssistenciaTecnicaCampo.md) agora é `frontend/app/atendimento-lista.tsx`,
// tela própria. Esta tela (`os-lista.tsx`) não perdeu nenhuma capacidade
// nem mudou de comportamento — continua sendo a lista completa de O.S. da
// retaguarda (filtros tradicionais De/Até, hoje também acessível no
// mobile), só deixou de ser a porta de entrada do tile "Atendimento de
// Campo" (`ModuleTiles.tsx` aponta pra `/atendimento-lista` agora).
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Modal, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { cacheOsParaOffline, purgarCacheExpirado } from "@/src/utils/storage/offlineAtendimento";
import { syncTodasFilasPendentes } from "@/src/utils/offlineSync/atendimentoSync";
import { apiGet } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;
type OSRow = {
  codigo: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente_nome: string; atendente_nome: string;
  tecnico_responsavel: number | null; tecnico_nome: string;
  auxiliar_tecnico: number | null; auxiliar_nome: string;
  checkin_em: string | null; checkout_em: string | null; proxima_agenda: string | null;
};
type EquipamentoRow = { codigo: number; equipamento: number | null; numero_de_serie: string; marca_descricao: string | null; modelo_descricao: string | null };
type HistoricoItem = { codigo: number; data: string | null; situacao: string; resumo: string };

const SITUACOES = [
  { value: "", label: "Todas" },
  { value: "A", label: "Aberta" },
  { value: "F", label: "Fechada" },
  { value: "PG", label: "Faturada" },
  { value: "C", label: "Cancelada" },
];

// "2026-08-14T13:33:45.667000" → "14/08 13:33" (compacto, pra caber numa
// pill de linha de lista — diferente do card cheio de os-geral.tsx, que usa
// formatCheckinDateTime com o ano).
function fmtPillDateTime(iso: string | null): string {
  if (!iso) return "";
  const [datePart, timePart] = iso.split("T");
  const [, m, d] = (datePart || "").split("-");
  const hm = (timePart || "").slice(0, 5);
  return d ? `${d}/${m}${hm ? ` ${hm}` : ""}` : iso;
}

// "Atendimento parado" — check-in feito, sem check-out, há mais de 2h.
// Mesmo espírito do `isStale` do Painel de Pedidos (`app/pedidos.tsx`),
// adaptado pra escala de horas (não dias, já que check-in/check-out é uma
// única visita, não um pedido em aberto por dias) — sinal só visual na
// pill (não reordena a lista, diferente do Painel de Pedidos), já que
// aqui não há colunas por tipo cuja cor precise ser preservada (a
// correção de 2026-08-11 do Painel de Pedidos — não sobrescrever a cor da
// coluna com vermelho — não se aplica aqui, não existe cor de coluna).
const CHECKIN_STALE_MS = 2 * 60 * 60 * 1000;

function parseIsoToMs(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

function fmtDecorrido(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60000));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h}h${m > 0 ? `${m}min` : ""}` : `${m}min`;
}

export default function OSListaScreen() {
  const router = useRouter();
  const { can, classe, isMaster, usuarioCodigo, moduleOn } = usePermissions();
  const feedback = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!(can("OS_COMP.ABRIR") || can("OS_ATENDIMENTO.ABRIR"))) {
    return <LockedView testID="os-lista-sem-permissao" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [tecnico, setTecnico] = useState<number | null>(null);
  const [auxiliar, setAuxiliar] = useState<number | null>(null);
  const [funcOptions, setFuncOptions] = useState<SelectOption[]>([]);
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [items, setItems] = useState<OSRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);

  // Relógio ÚNICO compartilhado por todas as linhas (não 1 setInterval por
  // linha — podem ser dezenas) pra recalcular "atendimento parado" ao vivo,
  // mesmo padrão de `nowMs` em app/pedidos.tsx.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 10000);
    return () => clearInterval(t);
  }, []);

  const usuarioCod = isMaster ? -2 : (usuarioCodigo ?? -2);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      if (c) {
        try {
          const base = c.api.replace(/\/+$/, "");
          const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const j = await fetch(`${base}/api/funcionarios?${qs}`).then((r) => r.json());
          const fs: { codigo: number; nome: string; nome_guerra: string }[] = Array.isArray(j?.items) ? j.items : [];
          setFuncOptions(fs.map((f) => ({ value: f.codigo, label: f.nome_guerra || f.nome || `#${f.codigo}` })));
        } catch {
          // silencioso
        }
      }
      setLoadingConn(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pré-carga automática pra Sincronização Offline (Atendimento de Campo
  // — ver AssistenciaTecnicaCampo.md) — decisão do usuário, 2026-08-14:
  // toda OS que aparece nesta lista, com internet, fica salva localmente
  // sozinha, sem ação manual. Roda em segundo plano (nunca aguardada,
  // nunca bloqueia a UI), sequencial e silenciosa — falha de rede aqui é
  // só "não pré-carregou esta OS", nunca um erro pro usuário ver. Só faz
  // sentido pro módulo Assistência (o offline é específico do fluxo de
  // Atendimento de Campo, Oficina não usa `os-atendimento.tsx`).
  // Sincroniza TODA fila pendente do dispositivo (todas as OS's visitadas
  // offline, não só as da página atual) assim que a lista carrega com
  // conexão — achado de revisão Gauntlet retroativa, 2026-08-14: antes,
  // só a OS aberta na tela de Atendimento sincronizava, então um técnico
  // que visitava várias OS's offline e só reabria o app na Lista depois
  // (não em cada OS individualmente) nunca sincronizava nada. Best-effort/
  // silencioso — não bloqueia a lista, não mostra erro pro usuário aqui
  // (um conflito fica marcado na fila e só reaparece com o banner
  // bloqueante certo quando essa OS específica for reaberta). Também
  // purga o cache local expirado (LGPD — dado de cliente/GPS não fica
  // salvo indefinidamente no aparelho, ver `purgarCacheExpirado`).
  const sincronizarEPurgar = useCallback(async (c: Conn) => {
    if (!moduleOn("Assistencia")) return;
    syncTodasFilasPendentes(c);
    purgarCacheExpirado();
  }, [moduleOn]);

  const prefetchOffline = useCallback(async (c: Conn, rows: OSRow[]) => {
    if (!moduleOn("Assistencia")) return;
    for (const row of rows) {
      try {
        const j = await apiGet(c, `/api/os-completo/${row.codigo}`);
        if (!j?.success || !j.os) continue;
        const equipJ = await apiGet(c, `/api/os-completo/${row.codigo}/equipamentos`);
        const statusJ = await apiGet(c, `/api/status-os`);
        await cacheOsParaOffline(row.codigo, {
          os: j.os,
          equipamentos: equipJ?.success ? equipJ.items || [] : [],
          historico: [],
          statusOsOptions: statusJ?.success
            ? (statusJ.items || []).map((s: { codigo: number; descricao: string }) => ({ value: s.codigo, label: s.descricao }))
            : [],
          versaoAtendimento: (j.os.versao_atendimento as string | undefined) ?? null,
        });
      } catch {
        // silencioso — ver comentário acima
      }
    }
  }, [moduleOn]);

  const load = useCallback(async (
    c: Conn, term: string, sit: string, tec: number | null, aux: number | null,
    di: string | null, df: string | null, pg: number, append: boolean,
  ) => {
    if (aborter.current) aborter.current.abort();
    const ac = new AbortController();
    aborter.current = ac;
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/os`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: c.servidor, banco: c.banco,
          search: term, situacao: sit, tecnico: tec, auxiliar: aux,
          data_ini: di, data_fim: df, page: pg, size: 20,
          classe, master: isMaster, usuario_codigo: usuarioCod,
        }),
        signal: ac.signal,
      });
      const j = await r.json();
      if (!j?.success) {
        feedback.showError(j?.message || "Falha na consulta.");
        if (!append) setItems([]);
      } else {
        setItems((prev) => (append ? [...prev, ...j.items] : j.items));
        setTotal(j.total || 0);
        prefetchOffline(c, j.items || []);
        sincronizarEPurgar(c);
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError") {
        feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    } finally {
      if (aborter.current === ac) setLoading(false);
    }
  }, [feedback, classe, isMaster, usuarioCod, prefetchOffline, sincronizarEPurgar]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => { setPage(1); load(conn, search, situacao, tecnico, auxiliar, dataIni, dataFim, 1, false); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, search, situacao, tecnico, auxiliar, dataIni, dataFim]);

  const loadMore = () => {
    if (!conn || loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(conn, search, situacao, tecnico, auxiliar, dataIni, dataFim, next, true);
  };

  const abrirOS = (item: OSRow) => {
    router.push({ pathname: isWeb ? "/os-geral" : "/os-atendimento", params: { os: String(item.codigo) } } as never);
  };

  const [equipModalOs, setEquipModalOs] = useState<number | null>(null);

  const canGravar = can("OS_COMP.GRAVAR");

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="os-lista-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="os-lista-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>O.S. ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.shellOuter}>
        <View style={styles.shell}>
          <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="os-lista-filtros" style={styles.accordionOuter}>
            <View style={styles.filterCard}>
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder="Buscar por cliente ou nº da O.S.…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  testID="os-lista-search"
                />
              </View>
              <View style={styles.chipsRow}>
                {SITUACOES.map((s) => {
                  const sel = situacao === s.value;
                  return (
                    <Pressable
                      key={s.value || "all"}
                      onPress={() => setSituacao(s.value)}
                      style={[styles.chip, sel && styles.chipSel]}
                      testID={`os-lista-chip-${s.value || "all"}`}
                    >
                      <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Técnico</Text>
                  <SelectField
                    value={tecnico}
                    onChange={(v) => setTecnico(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Todos"
                    allowClear
                    compactWeb
                    testID="os-lista-filtro-tecnico"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Auxiliar</Text>
                  <SelectField
                    value={auxiliar}
                    onChange={(v) => setAuxiliar(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Todos"
                    allowClear
                    compactWeb
                    testID="os-lista-filtro-auxiliar"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>De</Text>
                  <WebDateField
                    value={dataIni}
                    onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                    testID="os-lista-data-ini"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Até</Text>
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="os-lista-data-fim" />
                </View>
              </View>
            </View>
          </AccordionSection>

          {loading && items.length === 0 ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          <FlatList
            data={items}
            keyExtractor={(i) => String(i.codigo)}
            contentContainerStyle={styles.listContent}
            onEndReached={loadMore}
            onEndReachedThreshold={0.4}
            ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhuma O.S. encontrada.</Text> : null}
            renderItem={({ item }) => {
              const checkinMs = parseIsoToMs(item.checkin_em);
              const isCheckinStale = checkinMs != null && !item.checkout_em && (nowMs - checkinMs) > CHECKIN_STALE_MS;
              return (
              <Pressable onPress={() => abrirOS(item)} style={styles.row} testID={`os-lista-${item.codigo}`}>
                <View style={styles.rowTop}>
                  <Text style={styles.rowTitle} numberOfLines={1}>#{item.codigo} · {item.cliente_nome || "(sem cliente)"}</Text>
                  <Text style={styles.rowValor}>{formatBRL(item.total)}</Text>
                </View>
                <View style={styles.pillsRow}>
                  <View style={[styles.pill, styles.pillSituacao]}>
                    <Text style={styles.pillText}>{item.situacao_label}</Text>
                  </View>
                  <Text style={styles.rowSub}>{item.data ? formatDateBR(item.data) : "—"}</Text>
                  {item.tecnico_nome ? (
                    <View style={styles.pill}><Text style={styles.pillText}>Téc: {item.tecnico_nome}</Text></View>
                  ) : null}
                  {item.auxiliar_nome ? (
                    <View style={styles.pill}><Text style={styles.pillText}>Aux: {item.auxiliar_nome}</Text></View>
                  ) : null}
                  {item.checkin_em ? (
                    <View style={[styles.pill, styles.pillOk, isCheckinStale && styles.pillStale]} testID={isCheckinStale ? `os-lista-${item.codigo}-checkin-parado` : undefined}>
                      <Ionicons
                        name={isCheckinStale ? "alert-circle-outline" : "log-in-outline"}
                        size={11}
                        color={isCheckinStale ? colors.error : colors.success}
                      />
                      <Text style={[styles.pillText, { color: isCheckinStale ? colors.error : colors.success }]}>
                        {isCheckinStale ? `Em campo há ${fmtDecorrido(nowMs - checkinMs!)}` : fmtPillDateTime(item.checkin_em)}
                      </Text>
                    </View>
                  ) : null}
                  {item.checkout_em ? (
                    <View style={[styles.pill, styles.pillOk]}>
                      <Ionicons name="log-out-outline" size={11} color={colors.success} />
                      <Text style={[styles.pillText, { color: colors.success }]}>{fmtPillDateTime(item.checkout_em)}</Text>
                    </View>
                  ) : null}
                  {item.proxima_agenda ? (
                    <View style={styles.pill}>
                      <Ionicons name="calendar-outline" size={11} color={colors.muted} />
                      <Text style={styles.pillText}>{formatDateBR(item.proxima_agenda)}</Text>
                    </View>
                  ) : null}
                  <Pressable
                    onPress={(e) => { e.stopPropagation(); setEquipModalOs(item.codigo); }}
                    style={styles.equipIconBtn}
                    hitSlop={8}
                    testID={`os-lista-${item.codigo}-equipamentos`}
                  >
                    <Ionicons name="hardware-chip-outline" size={16} color={colors.brandPrimary} />
                  </Pressable>
                </View>
              </Pressable>
              );
            }}
          />
        </View>
      </View>

      {canGravar && isWeb ? (
        <Pressable onPress={() => router.push("/os-geral" as never)} style={styles.fab} testID="os-lista-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <EquipamentosHistoricoModal osId={equipModalOs} conn={conn} onClose={() => setEquipModalOs(null)} />
    </SafeAreaView>
  );
}

// Modal leve "Equipamentos/Histórico" por linha — busca os equipamentos
// vinculados à OS sob demanda (ao abrir) e, ao tocar num deles, o histórico
// de OS já atendidas naquele equipamento. Reaproveita só endpoints já
// existentes (nenhum endpoint novo pra isto).
function EquipamentosHistoricoModal({ osId, conn, onClose }: { osId: number | null; conn: Conn | null; onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [equipamentos, setEquipamentos] = useState<EquipamentoRow[]>([]);
  const [expandido, setExpandido] = useState<number | null>(null);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [historicoLoading, setHistoricoLoading] = useState(false);

  useEffect(() => {
    if (!osId || !conn) { setEquipamentos([]); setExpandido(null); return; }
    setLoading(true);
    const base = conn.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
    fetch(`${base}/api/os-completo/${osId}/equipamentos?${qs}`)
      .then((r) => r.json())
      .then((j) => setEquipamentos(j?.success ? j.items || [] : []))
      .catch(() => setEquipamentos([]))
      .finally(() => setLoading(false));
  }, [osId, conn]);

  const abrirHistorico = (equipamento: number) => {
    if (!conn) return;
    setExpandido(equipamento);
    setHistoricoLoading(true);
    const base = conn.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
    fetch(`${base}/api/equipamentos/${equipamento}/historico-os?${qs}`)
      .then((r) => r.json())
      .then((j) => setHistorico(j?.success ? j.items || [] : []))
      .catch(() => setHistorico([]))
      .finally(() => setHistoricoLoading(false));
  };

  return (
    <Modal visible={!!osId} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={modalStyles.bg} onPress={onClose}>
        <Pressable style={modalStyles.card} onPress={(e) => e.stopPropagation()}>
          <View style={modalStyles.header}>
            <Text style={modalStyles.title}>Equipamentos da OS #{osId}</Text>
            <Pressable onPress={onClose} hitSlop={8} testID="os-lista-equip-modal-fechar">
              <Ionicons name="close" size={20} color={colors.muted} />
            </Pressable>
          </View>
          {loading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
          {!loading && equipamentos.length === 0 ? (
            <Text style={modalStyles.empty}>Nenhum equipamento vinculado.</Text>
          ) : null}
          {equipamentos.map((eq) => (
            <View key={eq.codigo}>
              <Pressable
                onPress={() => (eq.equipamento ? abrirHistorico(eq.equipamento) : undefined)}
                style={modalStyles.equipRow}
                testID={`os-lista-equip-modal-item-${eq.codigo}`}
              >
                <Text style={modalStyles.equipNome} numberOfLines={1}>
                  {eq.numero_de_serie}{eq.marca_descricao ? ` · ${eq.marca_descricao}` : ""} {eq.modelo_descricao || ""}
                </Text>
                <Ionicons name={expandido === eq.equipamento ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
              </Pressable>
              {expandido === eq.equipamento ? (
                <View style={modalStyles.historicoBox}>
                  {historicoLoading ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : null}
                  {!historicoLoading && historico.length === 0 ? (
                    <Text style={modalStyles.empty}>Sem histórico.</Text>
                  ) : null}
                  {historico.map((h) => (
                    <Text key={h.codigo} style={modalStyles.historicoLine} numberOfLines={1}>
                      OS #{h.codigo} · {h.data || "—"} · {h.situacao} {h.resumo ? `· ${h.resumo}` : ""}
                    </Text>
                  ))}
                </View>
              ) : null}
            </View>
          ))}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const modalStyles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", paddingHorizontal: spacing.xl },
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg, maxWidth: 480, width: "100%", alignSelf: "center", maxHeight: "80%",
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  empty: { fontSize: 13, color: colors.muted, fontStyle: "italic", paddingVertical: spacing.sm },
  equipRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border,
  },
  equipNome: { flex: 1, fontSize: 13, color: colors.onSurface },
  historicoBox: { paddingLeft: spacing.md, paddingBottom: spacing.sm, gap: 4 },
  historicoLine: { fontSize: 12, color: colors.muted },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  shellOuter: { flex: 1, alignItems: "center" },
  shell: { ...WEB_CONTENT_SHELL, flex: 1 },
  scrollWeb: WEB_SCROLL_CENTER,
  accordionOuter: { marginTop: spacing.md, marginBottom: spacing.sm },
  filterCard: { ...WEB_FILTER_CARD, marginTop: spacing.sm, gap: spacing.sm },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  colNarrow: { width: 160 },
  label: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: 100, gap: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  // Card responsivo: linha 1 fixa (nº+cliente / valor), linha 2 em
  // flexWrap com "pills" — quebra naturalmente em tela estreita (mobile)
  // em vez de estourar horizontalmente como o layout rígido anterior.
  row: {
    alignSelf: "stretch", width: "100%",
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, gap: spacing.xs,
  },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  rowTitle: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  pillsRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 },
  pill: {
    flexDirection: "row", alignItems: "center", gap: 3,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  pillSituacao: { backgroundColor: colors.brandPrimary + "18", borderColor: colors.brandPrimary },
  pillOk: { borderColor: colors.success },
  // Check-in feito há mais de CHECKIN_STALE_MS sem check-out — sinal
  // visual só nesta pill (não reordena a lista, não sobrescreve outra
  // cor — ver comentário em CHECKIN_STALE_MS).
  pillStale: { borderColor: colors.error, backgroundColor: colors.error + "14" },
  pillText: { fontSize: 11, color: colors.onSurface },
  equipIconBtn: { marginLeft: "auto", padding: 4 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
});
