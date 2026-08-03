// Financeiro > Fluxo de Caixa > Contas x Funcionário (FrmConFunc.frm,
// "Acesso das Contas Por Funcionários...") — configura quais Contas
// (caixa/banco) cada funcionário pode visualizar. Web-only, tela única
// compacta sem abas (mesmo padrão de contas.tsx/fornecedores.tsx — o
// .frm legado também não tem controle de aba).
//
// Só a tela de configuração foi construída nesta rodada — nenhuma tela
// consumidora (Geração de Boletos, futuro Painel de Movimentação/
// Previsão) foi retroalimentada pra FILTRAR contas por essa configuração
// ainda. Ver PENDENCIAS.md > "Contas x Funcionário".
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

type ContaItem = { codigo: number; descricao: string };
type FuncionarioOpt = { codigo: number; nome_guerra: string; situacao: string };

export default function ContaFuncionarioScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contas x Funcionário está disponível apenas no web." testID="conta-funcionario-web-only" />;
  }

  const canAbrir = can("CONTA_FUNC.ABRIR") || isMaster;
  const canGravar = can("CONTA_FUNC.GRAVAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [funcionarios, setFuncionarios] = useState<FuncionarioOpt[]>([]);
  const [funcionarioCod, setFuncionarioCod] = useState<number | null>(null);

  const [disponiveis, setDisponiveis] = useState<ContaItem[]>([]);
  const [vinculadas, setVinculadas] = useState<ContaItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      try {
        const j = await apiGet(c, "/api/funcionarios-cadastro", { search: "" });
        const ativos: FuncionarioOpt[] = (j?.items || []).filter((f: any) => f.situacao === "A");
        setFuncionarios(ativos);
      } catch { setFuncionarios([]); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const funcionarioOptions: SelectOption[] = useMemo(
    () => funcionarios.map((f) => ({ value: f.codigo, label: f.nome_guerra })),
    [funcionarios]
  );

  const carregarVinculo = useCallback(async (c: Connection, funcionario: number) => {
    setLoading(true);
    try {
      const j = await apiGet(c, "/api/conta-funcionario", { funcionario });
      if (j?.success) {
        const todas: ContaItem[] = j.contas || [];
        const vinculadosSet = new Set<number>(j.vinculadas || []);
        setDisponiveis(todas.filter((ct) => !vinculadosSet.has(ct.codigo)));
        setVinculadas(todas.filter((ct) => vinculadosSet.has(ct.codigo)));
      } else {
        setDisponiveis([]); setVinculadas([]);
        fb.showError(friendlyApiError(j, "Falha ao carregar contas."));
      }
    } catch (e) {
      setDisponiveis([]); setVinculadas([]);
      fb.showError(friendlyCatchError(e, "Falha ao carregar contas."));
    } finally {
      setLoading(false);
    }
  }, [fb]);

  const onSelecionarFuncionario = (v: string | number | null) => {
    const cod = v as number | null;
    setFuncionarioCod(cod);
    setDisponiveis([]); setVinculadas([]);
    if (cod && conn) carregarVinculo(conn, cod);
  };

  const mover = (item: ContaItem, para: "vinculadas" | "disponiveis") => {
    if (para === "vinculadas") {
      setDisponiveis((prev) => prev.filter((c) => c.codigo !== item.codigo));
      setVinculadas((prev) => [...prev, item].sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR")));
    } else {
      setVinculadas((prev) => prev.filter((c) => c.codigo !== item.codigo));
      setDisponiveis((prev) => [...prev, item].sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR")));
    }
  };

  const adicionarTodas = () => {
    if (disponiveis.length === 0) return;
    setVinculadas((prev) => [...prev, ...disponiveis].sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR")));
    setDisponiveis([]);
  };
  const removerTodas = () => {
    if (vinculadas.length === 0) return;
    setDisponiveis((prev) => [...prev, ...vinculadas].sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR")));
    setVinculadas([]);
  };

  const gravar = async () => {
    if (!conn) return;
    if (!funcionarioCod) { fb.showWarning("Selecione o funcionário."); return; }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/conta-funcionario", "POST", {
        ...auditCtx, servidor: conn.servidor, banco: conn.banco,
        funcionario: funcionarioCod, contas: vinculadas.map((c) => c.codigo),
      });
      if (j?.success) {
        fb.showSuccess(`Registro gravado — ${j.qtd} conta(s) liberada(s) para este funcionário.`);
      } else {
        fb.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar."));
    } finally {
      setSaving(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar esta tela." testID="conta-funcionario-locked" />;
  }

  const semFuncionario = !funcionarioCod;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="conta-funcionario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Contas x Funcionário</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} />
        {canGravar ? (
          <Pressable onPress={gravar} disabled={saving || semFuncionario} style={[styles.saveBtn, (saving || semFuncionario) && { opacity: 0.6 }]} testID="conta-funcionario-gravar">
            {saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        ) : null}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={[styles.filters, styles.filtersWeb]}>
            <Text style={styles.label}>Funcionário *</Text>
            <SelectField value={funcionarioCod} onChange={onSelecionarFuncionario} options={funcionarioOptions} placeholder="Selecione o funcionário…" compactWeb testID="conta-funcionario-funcionario" />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} /> : null}

          {!loading && !semFuncionario ? (
            <>
              <View style={styles.rowFields}>
                <Pressable onPress={adicionarTodas} disabled={disponiveis.length === 0} style={[styles.secondaryBtn, disponiveis.length === 0 && { opacity: 0.5 }]} testID="conta-funcionario-adicionar-todas">
                  <Text style={styles.secondaryBtnText}>Adicionar Todas</Text>
                </Pressable>
                <Pressable onPress={removerTodas} disabled={vinculadas.length === 0} style={[styles.secondaryBtn, vinculadas.length === 0 && { opacity: 0.5 }]} testID="conta-funcionario-remover-todas">
                  <Text style={styles.secondaryBtnText}>Remover Todas</Text>
                </Pressable>
              </View>

              <View style={styles.listsRow}>
                <View style={styles.listCard}>
                  <Text style={styles.listTitle}>Contas Disponíveis ({disponiveis.length})</Text>
                  {disponiveis.length === 0 ? <Text style={styles.empty}>Nenhuma conta disponível.</Text> : null}
                  {disponiveis.map((ct) => (
                    <Pressable key={ct.codigo} onPress={() => mover(ct, "vinculadas")} style={styles.listItem} testID={`conta-funcionario-disp-${ct.codigo}`}>
                      <Text style={styles.listItemText} numberOfLines={1}>{ct.descricao}</Text>
                      <Ionicons name="arrow-forward-circle-outline" size={20} color={colors.brandPrimary} />
                    </Pressable>
                  ))}
                </View>

                <View style={styles.listCard}>
                  <Text style={styles.listTitle}>Contas c/ Acesso ({vinculadas.length})</Text>
                  {vinculadas.length === 0 ? <Text style={styles.empty}>Nenhuma conta liberada.</Text> : null}
                  {vinculadas.map((ct) => (
                    <Pressable key={ct.codigo} onPress={() => mover(ct, "disponiveis")} style={styles.listItem} testID={`conta-funcionario-vinc-${ct.codigo}`}>
                      <Ionicons name="arrow-back-circle-outline" size={20} color={colors.brandPrimary} />
                      <Text style={styles.listItemText} numberOfLines={1}>{ct.descricao}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            </>
          ) : null}

          {!loading && semFuncionario ? (
            <Text style={styles.empty}>Selecione um funcionário para configurar suas contas.</Text>
          ) : null}
        </View>
      </ScrollView>

      <AppModal visible={ajudaOpen} transparent animationType="fade" onRequestClose={() => setAjudaOpen(false)}>
        <Pressable style={styles.helpBg} onPress={() => setAjudaOpen(false)}>
          <Pressable style={styles.helpCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.helpHeader}>
              <Text style={styles.helpTitle}>Ajuda — Contas x Funcionário</Text>
              <Pressable onPress={() => setAjudaOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Pra que serve{"\n"}</Text>
              Define quais contas de caixa/banco cada funcionário pode visualizar em telas que mostram
              informações por conta (ex.: Geração de Boletos, e futuramente Painel de Movimentação e Previsão).
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Como usar{"\n"}</Text>
              Escolha o funcionário, toque numa conta em "Contas Disponíveis" para liberar o acesso (ela
              passa para "Contas c/ Acesso"), ou toque numa conta já liberada para remover o acesso. Use
              "Adicionar Todas"/"Remover Todas" para mover a lista inteira de uma vez. Clique em "Gravar" no
              topo da tela para confirmar.
            </Text>
            <Text style={styles.helpItem}>
              <Text style={styles.helpItemTitle}>Sem nenhuma conta marcada{"\n"}</Text>
              Gravar sem nenhuma conta em "Contas c/ Acesso" remove todo o acesso do funcionário às contas —
              use "Remover Todas" só se essa for realmente a intenção.
            </Text>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, gap: spacing.sm,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  saveBtn: {
    backgroundColor: "rgba(255,255,255,0.18)", borderWidth: 1, borderColor: "rgba(255,255,255,0.3)",
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  saveLabel: { color: "#fff", fontWeight: "700", fontSize: 13 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  label: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "600" },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.md,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  listsRow: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  listCard: {
    flex: 1, minWidth: 260, padding: spacing.sm, borderRadius: radius.md,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, gap: 4,
  },
  listTitle: { fontSize: 12, fontWeight: "700", color: colors.muted, marginBottom: 4 },
  listItem: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 6,
    paddingVertical: 8, paddingHorizontal: 8, borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary, marginBottom: 4,
  },
  listItemText: { flex: 1, fontSize: 13, color: colors.onSurface },
  empty: { fontSize: 12, color: colors.muted, textAlign: "center", paddingVertical: spacing.sm },
  helpBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center" },
  helpCard: { width: "100%", maxWidth: 560, maxHeight: "80%", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg },
  helpHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  helpTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  helpItem: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.sm, lineHeight: 19 },
  helpItemTitle: { fontWeight: "700", color: colors.onSurface },
});
