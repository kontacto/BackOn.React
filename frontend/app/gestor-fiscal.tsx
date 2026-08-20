// Hub "Gestor Fiscal" (2026-08-20, user-directed) — aberto pelo Card
// "Gestor Fiscal" em app/(tabs)/transacoes.tsx. Reúne as telas de emissão/
// consulta fiscal do sistema, mesmo agrupamento do menu real "Transações >
// Notas Fiscais" do VB6 (confirmado pelo usuário, lista colada ao vivo):
// Gerar Nfe Comanda, Recebimento, Gerar Nfe, Gestor NFSe, Gestor NFCe,
// Contingência NFe, Contingência NFCe, Inutilização de Faixa NFe/NFCe.
//
// Só as telas JÁ CONSTRUÍDAS ganham card aqui (mesmo padrão de
// `movimentacoes.tsx` — nunca placeholder pra tela que não existe ainda):
// Gerar Nfe Comanda (nfe-agrupada.tsx), Gerar NFe (nfe-avulsa.tsx), Gestor
// NFCe (gestor-nfce.tsx, já inclui Contingência NFCe embutida). Faltam:
// Recebimento (FrmtraRec.frm, módulo grande — nf_recebimento*/import XML,
// ver PENDENCIAS.md > "Recebimento" no Blueprint), Gestor NFSe (RPS
// municipal, Geral\FrmManNSe.frm — distinto do caminho Sefin Nacional/DPS
// já implementado via comanda), Contingência NFe (FrmConNFe.frm, própria
// — não confundir com Contingência NFCe, já embutida em Gestor NFCe),
// Inutilização de Faixa NFe (a parte NFCe já existe como ação dentro de
// Gestor NFCe). "Despacho de NF's" (FrmDesNf.frm) NÃO entra nesta lista —
// equipe VB6 confirmou que nunca foi colocada em uso real (ver
// PENDENCIAS.md, "Diferenças pra v2").
import { useMemo } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Entry = {
  key: string;
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  visible: boolean;
};

export default function GestorFiscalScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Gestor Fiscal está disponível apenas no web."
        testID="gestor-fiscal-web-only"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "gerar-nfe-comanda",
        label: "Gerar Nfe Comanda",
        hint: "Emite uma única NF-e cobrindo várias comandas faturadas do mesmo cliente",
        icon: "layers-outline",
        route: "/nfe-agrupada",
        visible: moduleOn("nfe_ws") && can("NFE_AGRUPADA.ABRIR"),
      },
      {
        key: "gerar-nfe",
        label: "Gerar Nfe",
        hint: "Emite uma NF-e avulsa digitada livremente, para qualquer natureza de operação",
        icon: "document-text-outline",
        route: "/nfe-avulsa",
        visible: moduleOn("nfe_ws") && can("NFE_AVULSA.ABRIR"),
      },
      {
        key: "gestor-nfce",
        label: "Gestor NFCe",
        hint: "Consulta situação no SEFAZ, cancela, inutiliza numeração e valida contingência de NFC-e",
        icon: "receipt-outline",
        route: "/gestor-nfce",
        visible: moduleOn("emite_nfce") && can("GESTOR_NFCE.ABRIR"),
      },
      {
        // "Notas Fiscais" (Manutenção — FrmManRec.frm) transferida de
        // Cadastros pra cá, 2026-08-20, user-directed ("TRANSFERIR NOTAS
        // FISCAIS DE CADASTRO PARA A GESTÃO FISCAL"). Continua sendo a
        // mesma tela de consulta/pós-emissão (DANFE/cancelar/carta de
        // correção/XML) — não confundir com Gerar Nfe/Gerar Nfe Comanda
        // (digitação de nota nova). Sem `moduleOn` — o legado não liga
        // esta tela a nenhum módulo fiscal específico, cobre qualquer
        // natureza de operação.
        key: "notas-fiscais",
        label: "Notas Fiscais",
        hint: "Manutenção de Notas Fiscais — consulta, criticar, cancelar (Fase 1, sem emissão fiscal)",
        icon: "file-tray-full-outline",
        route: "/notas-fiscais",
        visible: can("NOTAS_FISCAIS.ABRIR"),
      },
      {
        // "Contingência NFe" (2026-08-20, user-directed) — migração de
        // Geral\FrmConNFe.frm. Tela própria (não há "Gestor NFe" único
        // pra embutir, diferente de Contingência NFCe).
        key: "contingencia-nfe",
        label: "Contingência NFe",
        hint: "Abre/fecha um período de contingência (SEFAZ indisponível) para emissão de NF-e",
        icon: "cloud-offline-outline",
        route: "/contingencia-nfe",
        visible: moduleOn("nfe_ws") && can("CONT_NFE.ABRIR"),
      },
    ],
    [can, moduleOn]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="gestor-fiscal-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Gestor Fiscal</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="receipt-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhuma tela liberada para o seu grupo neste módulo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`gestor-fiscal-${e.key}`}
              >
                <View style={styles.cardIcon}>
                  <Ionicons name={e.icon} size={24} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardLabel}>{e.label}</Text>
                  <Text style={styles.cardHint}>{e.hint}</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.muted} />
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerSpacer: { width: 40 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webFrame: { width: "100%", maxWidth: 1240 },
  gridWeb: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  emptyCard: {
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    padding: spacing.xl,
    marginTop: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyCardWeb: { minHeight: 220 },
  empty: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 8 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  cardWeb: { flexBasis: "48%", minHeight: 96, paddingVertical: spacing.xl },
  cardIcon: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  cardLabel: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 13, color: colors.muted, marginTop: 2 },
});
