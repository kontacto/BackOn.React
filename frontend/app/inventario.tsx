// Painel de Inventário (Transações > Inventário) — Fase 1: núcleo manual
// (Abertura, Fechar, Cancelar; Digitação vive numa tela própria,
// `inventario-digitacao.tsx`). Legado: `FrmInvAbe.frm`,
// `Geral\Inventario.bas::Fecha_Inventario`/`Cancela_Inventario`. Ver
// PENDENCIAS.md > "Inventário" pro rastreio completo do ecossistema —
// regras de negócio, decisões de escopo (checkboxes Revenda/Consumo/
// Imobilizado da Abertura legada são código morto, não portadas; veículos
// entram no escopo; "Registro de Inventário" não portado, morto no
// legado) — antes de mexer neste arquivo.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import AjudaInventarioModal from "@/src/components/inventario/AjudaInventarioModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const TIPO_OPTIONS: SelectOption[] = [
  { value: "G", label: "Geral (pré-carrega todo o estoque atual)" },
  { value: "P", label: "Parcial (não pré-carrega nada, só ajusta o que for digitado)" },
  { value: "C", label: "Contábil (só o que for digitado entra na conferência)" },
];

function todayIso(): string {
  // NUNCA usar `new Date().toISOString().slice(0,10)` pra "data de hoje" —
  // toISOString() converte pra UTC antes de formatar, então em fusos
  // negativos (Brasil, UTC-3) qualquer horário local a partir de ~21h já
  // vira o dia SEGUINTE em UTC (achado ao vivo 2026-07-23: balanço aberto
  // no dia 22 mostrando data 23). getFullYear/getMonth/getDate são no fuso
  // LOCAL do navegador, sem essa conversão.
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function fmtMoneyBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type Status = {
  aberto: boolean;
  situacao_balanco: string;
  tipo_balanco: string;
  tipo_balanco_descricao: string;
  data_balanco: string | null;
  total_itens: number;
  itens_digitados: number;
};

export default function InventarioScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Inventário está disponível apenas no web."
        testID="inventario-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [dataAbertura, setDataAbertura] = useState<string>(todayIso());
  // Parcial é o padrão pré-selecionado (mesmo comportamento do combo do
  // legado, confirmado pelo usuário via a tela real do FrmInvAbe.frm,
  // 2026-07-23) — não Geral.
  const [tipoAbertura, setTipoAbertura] = useState<string | null>("P");
  const [abrindo, setAbrindo] = useState(false);
  // Qual ação está em andamento agora (só uma por vez) — mostra um
  // indicador de carregamento no botão certo, pra não parecer travado
  // durante uma operação que pode demorar alguns segundos (Fechamento
  // ajusta o estoque de todo item divergente). Achado ao vivo 2026-07-23:
  // sem nenhum feedback visual, o usuário reportou "cliquei e não
  // aconteceu nada" mesmo a ação tendo concluído com sucesso — o Fechamento
  // em si já foi otimizado (era loop por item, virou operação única em
  // SQL), mas o indicador continua valendo pra qualquer demora residual.
  const [processandoAcao, setProcessandoAcao] = useState<"abrir" | "fechar" | "cancelar" | null>(null);
  const processando = processandoAcao !== null;

  const podeAbrir = can("INVENTARIO.ABERTURA");
  const podeDigitar = can("INVENTARIO.DIGITACAO");
  const podeFechar = can("INVENTARIO.FECHAR");
  const podeCancelar = can("INVENTARIO.CANCELAR");
  const podeRelatorioContagem = can("INVENTARIO.REL_CONTAGEM");
  const podeRelatoriosFase2 =
    can("INVENTARIO.REL_CONFERENCIA") || can("INVENTARIO.REL_CRITICA") ||
    can("INVENTARIO.REL_RESULTADO") || can("INVENTARIO.REL_DIVERGENCIA");
  const podeVerDivergencia = can("INVENTARIO.REL_DIVERGENCIA");

  // Prévia de divergência sempre visível antes de Fechar (melhoria proposta
  // em cima do legado — PENDENCIAS.md > Inventário, regra 9: o Relatório de
  // Divergência é literalmente uma prévia do que o Fechamento vai lançar em
  // `movimentacao`/ajuste de estoque). Só um resumo (contagem + valor total
  // em preço de venda) — o relatório completo, com filtros, continua na
  // tela de Relatórios.
  const [divergencia, setDivergencia] = useState<{ count: number; total: number } | null>(null);

  const carregarStatus = useCallback(async (c: Connection) => {
    setLoading(true);
    try {
      const r = await apiGet(c, "/api/inventario/status");
      if (r?.success) setStatus(r);
      else fb.showError(friendlyApiError(r, "Não foi possível consultar o status do inventário."));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      carregarStatus(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    // Pedido explícito do usuário, 2026-07-23: mostrar sempre que houver
    // divergência, independente do tipo de balanço — reversão de uma
    // tentativa anterior de esconder isso pro tipo Contábil (que nunca
    // ajusta estoque no Fechamento). O texto do badge (abaixo, no render)
    // é que muda por tipo, pra não sugerir "o Fechar vai ajustar" quando
    // for Contábil.
    if (!conn || !status?.aberto || !podeVerDivergencia) {
      setDivergencia(null);
      return;
    }
    (async () => {
      const r = await apiGet(conn, "/api/inventario/relatorio-divergencia", { preco: "venda" });
      if (r?.success) {
        const lista = r.itens || [];
        setDivergencia({ count: lista.length, total: lista.reduce((s: number, it: any) => s + (it.preco_total || 0), 0) });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, status?.aberto, status?.data_balanco, status?.tipo_balanco, podeVerDivergencia]);

  const handleAbrir = useCallback(async () => {
    if (!conn) return;
    if (!dataAbertura) { fb.showError("Informe a data do balanço."); return; }
    if (!tipoAbertura) { fb.showError("Selecione o tipo de balanço."); return; }
    setProcessandoAcao("abrir");
    try {
      const r = await apiSend(conn, "/api/inventario/abrir", "POST", {
        data: dataAbertura, tipo: tipoAbertura, ...auditCtx,
      });
      if (r?.success) {
        fb.showSuccess(r.message || "Inventário aberto.");
        setAbrindo(false);
        carregarStatus(conn);
      } else {
        fb.showError(friendlyApiError(r, "Não foi possível abrir o inventário."));
      }
    } finally {
      setProcessandoAcao(null);
    }
  }, [conn, dataAbertura, tipoAbertura, auditCtx, fb, carregarStatus]);

  const handleFechar = useCallback(() => {
    if (!conn) return;
    fb.showConfirm(
      `Confirma o fechamento do balanço do dia ${status?.data_balanco ? new Date(status.data_balanco + "T00:00:00").toLocaleDateString("pt-BR") : ""}? ` +
        (status?.tipo_balanco === "C"
          ? "Balanço Contábil não altera o estoque."
          : status?.tipo_balanco === "P"
          ? "Os itens digitados com contagem divergente terão o estoque ajustado automaticamente — o restante do catálogo (não digitado) não é tocado."
          : "Os itens com contagem divergente terão o estoque ajustado automaticamente (inclusive os não digitados, que ficam zerados)."),
      async () => {
        setProcessandoAcao("fechar");
        try {
          const r = await apiSend(conn, "/api/inventario/fechar", "POST", { ...auditCtx });
          if (r?.success) {
            fb.showSuccess(r.message || "Inventário fechado.", undefined, 5000);
            carregarStatus(conn);
          } else {
            fb.showError(friendlyApiError(r, "Não foi possível fechar o inventário."));
          }
        } finally {
          setProcessandoAcao(null);
        }
      },
    );
  }, [conn, status, auditCtx, fb, carregarStatus]);

  const handleCancelar = useCallback(() => {
    if (!conn) return;
    fb.showConfirm(
      "Confirma o cancelamento do balanço aberto? Todos os itens já digitados serão perdidos, sem nenhum efeito no estoque.",
      async () => {
        setProcessandoAcao("cancelar");
        try {
          const r = await apiSend(conn, "/api/inventario/cancelar", "POST", { ...auditCtx });
          if (r?.success) {
            fb.showSuccess(r.message || "Inventário cancelado.");
            carregarStatus(conn);
          } else {
            fb.showError(friendlyApiError(r, "Não foi possível cancelar o inventário."));
          }
        } finally {
          setProcessandoAcao(null);
        }
      },
    );
  }, [conn, auditCtx, fb, carregarStatus]);

  // Texto do badge de divergência — 3 variantes por tipo de balanço,
  // porque o efeito do Fechamento é diferente pros 3 (ver `_fechar_sync` e
  // `_abrir_sync` em inventario_service.py): Contábil nunca ajusta
  // estoque; Geral ajusta TODO o catálogo (inclusive zerando o que não foi
  // digitado); Parcial ajusta só o que foi digitado, o resto do catálogo
  // fica intocado. Extraído numa variável própria (em vez de ternário
  // aninhado dentro do JSX) só por legibilidade.
  const divergenciaTexto = (() => {
    if (!divergencia) return "";
    const contagem = divergencia.count === 0
      ? "Nenhuma divergência até agora"
      : `${divergencia.count} ${divergencia.count === 1 ? "item divergente" : "itens divergentes"} até agora (valor ${fmtMoneyBRL(divergencia.total)})`;
    if (status?.tipo_balanco === "C") {
      return `${contagem}. Balanço Contábil não ajusta o estoque no Fechamento.`;
    }
    if (status?.tipo_balanco === "P") {
      return divergencia.count === 0
        ? `${contagem} — só os itens digitados entram no ajuste do Fechamento.`
        : `${contagem} — é o que o Fechamento vai ajustar no estoque (só os itens digitados; o resto do catálogo não é tocado). Toque para ver o Relatório de Divergência.`;
    }
    return divergencia.count === 0
      ? `${contagem} — Fechar não vai ajustar estoque nenhum.`
      : `${contagem} — é o que o Fechamento vai ajustar no estoque. Toque para ver o Relatório de Divergência.`;
  })();

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="inventario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back} testID="inventario-voltar">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Inventário</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline"
          label="Ajuda"
          onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary}
          size={22}
          testID="inventario-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {loading ? (
            <Text style={styles.muted}>Carregando...</Text>
          ) : status?.aberto ? (
            <View style={[styles.card, styles.cardWeb]}>
              <View style={styles.statusRow}>
                <Ionicons name="lock-open-outline" size={22} color={colors.warning} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>
                    Balanço {status.tipo_balanco_descricao} em aberto
                  </Text>
                  <Text style={styles.muted}>
                    Data: {status.data_balanco ? new Date(status.data_balanco + "T00:00:00").toLocaleDateString("pt-BR") : "-"}
                    {"  ·  "}
                    {/* Parcial não pré-carrega nada — total_itens sempre
                        igual a itens_digitados nesse tipo (toda linha em
                        `inventario` só existe porque foi digitada), então
                        "X de Y" seria redundante; mostra só X. */}
                    {status.tipo_balanco === "P"
                      ? `Total Digitados: ${status.itens_digitados} Produtos`
                      : `Total Digitados: ${status.itens_digitados} de ${status.total_itens} Produtos`}
                  </Text>
                </View>
              </View>

              {divergencia ? (
                <Pressable
                  style={styles.divergenciaBadge}
                  onPress={() => router.push("/inventario-relatorios?relatorio=divergencia")}
                  testID="inventario-divergencia-badge"
                >
                  <Ionicons name="swap-vertical-outline" size={16} color={colors.warning} />
                  <Text style={styles.divergenciaBadgeText}>{divergenciaTexto}</Text>
                </Pressable>
              ) : null}

              <View style={styles.actionsRow}>
                {podeDigitar ? (
                  <Pressable
                    style={styles.primaryBtn}
                    onPress={() => router.push("/inventario-digitacao")}
                    testID="inventario-digitar"
                  >
                    <Ionicons name="create-outline" size={16} color={colors.onBrandPrimary} />
                    <Text style={styles.primaryBtnText}>Digitação de Estoque</Text>
                  </Pressable>
                ) : null}
                {podeRelatorioContagem ? (
                  <Pressable
                    style={styles.secondaryBtn}
                    onPress={() => router.push("/inventario-relatorio-contagem")}
                    testID="inventario-relatorio-contagem"
                  >
                    <Ionicons name="list-outline" size={16} color={colors.onSurface} />
                    <Text style={styles.secondaryBtnText}>Relatório de Contagem</Text>
                  </Pressable>
                ) : null}
                {podeRelatoriosFase2 ? (
                  <Pressable
                    style={styles.secondaryBtn}
                    onPress={() => router.push("/inventario-relatorios")}
                    testID="inventario-relatorios"
                  >
                    <Ionicons name="bar-chart-outline" size={16} color={colors.onSurface} />
                    <Text style={styles.secondaryBtnText}>Relatórios</Text>
                  </Pressable>
                ) : null}
                {podeFechar ? (
                  <Pressable
                    style={[styles.secondaryBtn, processando && styles.btnDisabled]}
                    onPress={handleFechar}
                    disabled={processando}
                    testID="inventario-fechar"
                  >
                    {processandoAcao === "fechar" ? (
                      <ActivityIndicator size="small" color={colors.success} />
                    ) : (
                      <Ionicons name="checkmark-done-outline" size={16} color={colors.success} />
                    )}
                    <Text style={[styles.secondaryBtnText, { color: colors.success }]}>
                      {processandoAcao === "fechar" ? "Fechando…" : "Fechar Inventário"}
                    </Text>
                  </Pressable>
                ) : null}
                {podeCancelar ? (
                  <Pressable
                    style={[styles.secondaryBtn, processando && styles.btnDisabled]}
                    onPress={handleCancelar}
                    disabled={processando}
                    testID="inventario-cancelar"
                  >
                    {processandoAcao === "cancelar" ? (
                      <ActivityIndicator size="small" color={colors.error} />
                    ) : (
                      <Ionicons name="close-circle-outline" size={16} color={colors.error} />
                    )}
                    <Text style={[styles.secondaryBtnText, { color: colors.error }]}>
                      {processandoAcao === "cancelar" ? "Cancelando…" : "Cancelar Inventário"}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : (
            <View style={[styles.card, styles.cardWeb]}>
              <View style={styles.statusRow}>
                <Ionicons name="cube-outline" size={22} color={colors.brandPrimary} />
                <Text style={styles.cardTitle}>Nenhum balanço aberto no momento</Text>
              </View>

              {podeAbrir ? (
                abrindo ? (
                  <View style={{ gap: spacing.md, marginTop: spacing.md }}>
                    <View style={styles.rowFields}>
                      <View style={styles.colNarrow}>
                        <Text style={styles.fieldLabel}>Data do balanço</Text>
                        <WebDateField value={dataAbertura} onChange={(v) => setDataAbertura(v || todayIso())} testID="inventario-data" />
                      </View>
                      <View style={styles.colFlex}>
                        <Text style={styles.fieldLabel}>Tipo de balanço</Text>
                        <SelectField value={tipoAbertura} onChange={(v) => setTipoAbertura(v as string)} options={TIPO_OPTIONS} compactWeb testID="inventario-tipo" />
                      </View>
                    </View>
                    <View style={styles.actionsRow}>
                      <Pressable
                        style={[styles.primaryBtn, processando && styles.btnDisabled]}
                        onPress={handleAbrir}
                        disabled={processando}
                        testID="inventario-gravar-abertura"
                      >
                        {processandoAcao === "abrir" ? (
                          <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                        ) : (
                          <Ionicons name="lock-open-outline" size={16} color={colors.onBrandPrimary} />
                        )}
                        <Text style={styles.primaryBtnText}>
                          {processandoAcao === "abrir" ? "Abrindo…" : "Abrir Inventário"}
                        </Text>
                      </Pressable>
                      <Pressable style={styles.secondaryBtn} onPress={() => setAbrindo(false)} testID="inventario-cancelar-abertura">
                        <Text style={styles.secondaryBtnText}>Voltar</Text>
                      </Pressable>
                    </View>
                  </View>
                ) : (
                  <Pressable style={[styles.primaryBtn, { marginTop: spacing.md, alignSelf: "flex-start" }]} onPress={() => setAbrindo(true)} testID="inventario-abrir-form">
                    <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
                    <Text style={styles.primaryBtnText}>Abrir Inventário</Text>
                  </Pressable>
                )
              ) : (
                <Text style={styles.muted}>Você não tem permissão para abrir um novo balanço.</Text>
              )}
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaInventarioModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webFrame: { width: "100%", maxWidth: 720 },
  muted: { color: colors.muted, fontSize: 14 },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  cardWeb: WEB_FILTER_CARD,
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardTitle: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  divergenciaBadge: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.sm,
    backgroundColor: colors.warning + "1a", borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.warning,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    marginTop: spacing.sm,
  },
  divergenciaBadgeText: { flex: 1, fontSize: 12, color: colors.onSurface, lineHeight: 17 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  rowFields: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  colNarrow: { width: 200 },
  colFlex: { flex: 1, minWidth: 260 },
  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "600" },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  btnDisabled: { opacity: 0.6 },
});
