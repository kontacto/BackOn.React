// Lista de Atendimento por Calendário (Assistência Técnica — regras 6/7/10,
// AssistenciaTecnicaCampo.md seção 8) — TELA INICIAL do app do técnico:
// calendário no topo (dia selecionado, default hoje) + lista dos
// atendimentos daquele dia, filtrando por `os.data_agendamento` (coluna
// legada reativada 2026-08-15, marcada na retaguarda via os-geral.tsx —
// ver "Data Agendada"/"Hora Agendada" naquele arquivo).
//
// Reverte a decisão de 2026-08-14 (estender `os-lista.tsx` genérico em vez
// de tela dedicada) — confirmado explicitamente com o usuário. `os-lista.tsx`
// continua existindo tal como está, sem nenhuma mudança de comportamento,
// só deixou de ser a porta de entrada mobile (ver seu comentário de topo).
//
// Ler QR Code continua caminho alternativo (regra 8) — ícone no cabeçalho
// leva pro scanner de `os-atendimento.tsx` (sem `?os=`).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import AtendimentoCalendario from "@/src/components/atendimento/AtendimentoCalendario";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;
type OSRow = {
  codigo: number; cliente_nome: string; situacao_label: string; total: number;
  tecnico_nome: string; auxiliar_nome: string; checkin_em: string | null; checkout_em: string | null;
  hora_agendamento: string;
};

const pad2 = (n: number) => String(n).padStart(2, "0");
const hojeIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
};

function fmtPillDateTime(iso: string | null): string {
  if (!iso) return "";
  const [datePart, timePart] = iso.split("T");
  const [, m, d] = (datePart || "").split("-");
  const hm = (timePart || "").slice(0, 5);
  return d ? `${d}/${m}${hm ? ` ${hm}` : ""}` : iso;
}

const AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Calendário",
    texto: "Escolha um dia para ver os atendimentos marcados para aquela data. O dia de hoje já vem selecionado.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Toque num atendimento",
    texto: "Abre direto a OS daquele cliente, pronta para check-in.",
    icon: { lib: "ion", name: "document-text-outline" },
  },
  {
    titulo: "Ler QR Code",
    texto: "Caminho alternativo: se você já está no local e quer ler o QR Code do equipamento em vez de escolher pela lista, use este ícone.",
    icon: { lib: "ion", name: "qr-code-outline" },
  },
];

export default function AtendimentoListaScreen() {
  const router = useRouter();
  const { can, classe, isMaster, usuarioCodigo } = usePermissions();
  const feedback = useFeedback();
  const isWeb = Platform.OS === "web";

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [selecionado, setSelecionado] = useState(hojeIso());
  const [items, setItems] = useState<OSRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const usuarioCod = isMaster ? -2 : (usuarioCodigo ?? -2);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      setLoadingConn(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (c: Conn, dia: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/os`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: c.servidor, banco: c.banco,
          data_agenda: dia, page: 1, size: 100,
          classe, master: isMaster, usuario_codigo: usuarioCod,
        }),
      });
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha na consulta."); setItems([]); return; }
      setItems(j.items || []);
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [feedback, classe, isMaster, usuarioCod]);

  useEffect(() => { if (conn) load(conn, selecionado); }, [conn, selecionado, load]);

  const abrirOS = (item: OSRow) => {
    router.push({ pathname: isWeb ? "/os-geral" : "/os-atendimento", params: { os: String(item.codigo) } } as never);
  };

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  if (!can("OS_ATENDIMENTO.ABRIR")) {
    return <SafeAreaView style={styles.safe} edges={["top"]}><LockedView /></SafeAreaView>;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="atendimento-lista-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="atendimento-lista-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>Atendimento de Campo</Text>
        <IconButtonWithTooltip
          icon="qr-code-outline" label="Ler QR Code" onPress={() => router.push("/os-atendimento" as never)}
          color={colors.onBrandPrimary} testID="atendimento-lista-qr"
        />
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary} testID="atendimento-lista-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} testID="atendimento-lista-scroll">
        <AtendimentoCalendario
          selecionado={selecionado}
          onSelecionarDia={setSelecionado}
          testID="atendimento-lista-calendario"
        />

        <Text style={styles.diaTitulo}>
          {formatDateBR(selecionado)} {selecionado === hojeIso() ? "(hoje)" : ""}
        </Text>

        {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.md }} /> : null}

        {!loading && items.length === 0 ? (
          <Text style={styles.empty}>Nenhum atendimento agendado para {formatDateBR(selecionado)}.</Text>
        ) : null}

        {!loading && items.map((item) => (
          <Pressable
            key={item.codigo}
            onPress={() => abrirOS(item)}
            style={styles.row}
            testID={`atendimento-lista-${item.codigo}`}
          >
            <View style={styles.rowTop}>
              <Text style={styles.rowTitle} numberOfLines={1}>#{item.codigo} · {item.cliente_nome || "(sem cliente)"}</Text>
              <Text style={styles.rowValor}>{formatBRL(item.total)}</Text>
            </View>
            <View style={styles.pillsRow}>
              <View style={[styles.pill, styles.pillSituacao]}>
                <Text style={styles.pillText}>{item.situacao_label}</Text>
              </View>
              {item.hora_agendamento ? (
                <View style={styles.pill}>
                  <Ionicons name="time-outline" size={11} color={colors.muted} />
                  <Text style={styles.pillText}>{item.hora_agendamento}</Text>
                </View>
              ) : null}
              {item.tecnico_nome ? (
                <View style={styles.pill}><Text style={styles.pillText}>Téc: {item.tecnico_nome}</Text></View>
              ) : null}
              {item.auxiliar_nome ? (
                <View style={styles.pill}><Text style={styles.pillText}>Aux: {item.auxiliar_nome}</Text></View>
              ) : null}
              {item.checkin_em ? (
                <View style={[styles.pill, styles.pillOk]}>
                  <Ionicons name="log-in-outline" size={11} color={colors.success} />
                  <Text style={[styles.pillText, { color: colors.success }]}>{fmtPillDateTime(item.checkin_em)}</Text>
                </View>
              ) : null}
              {item.checkout_em ? (
                <View style={[styles.pill, styles.pillOk]}>
                  <Ionicons name="log-out-outline" size={11} color={colors.success} />
                  <Text style={[styles.pillText, { color: colors.success }]}>{fmtPillDateTime(item.checkout_em)}</Text>
                </View>
              ) : null}
            </View>
          </Pressable>
        ))}
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Atendimento de Campo" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  diaTitulo: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  empty: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: spacing.lg },
  row: {
    alignSelf: "stretch", width: "100%",
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, gap: spacing.xs,
  },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  rowTitle: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  pillsRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 },
  pill: {
    flexDirection: "row", alignItems: "center", gap: 3,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  pillSituacao: { backgroundColor: colors.brandPrimary + "18", borderColor: colors.brandPrimary },
  pillOk: { borderColor: colors.success },
  pillText: { fontSize: 11, color: colors.onSurface },
});
