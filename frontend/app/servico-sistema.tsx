import React, { useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { useServicoSistemaForm } from "@/src/hooks/useServicoSistemaForm";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

// Modo Didático (CLAUDE.md > "Padrões de UI" > seção 4-5) — pedido
// explícito do usuário, 2026-08-26. Reaproveita o mesmo AjudaPedidoModal
// já usado em Pedido Bar/Geral e Controle do Sistema, com conteúdo
// próprio — endereça de propósito a confusão real que motivou o pedido:
// o campo "URL do manifest" não é o link do repositório GitHub do
// projeto, é o link do arquivo publicado no Blob de distribuição da
// Kontacto (ver updater/publish/README.md).
const SERVICO_SISTEMA_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "URL do manifest (credencial)",
    texto:
      "NÃO é o endereço do repositório no GitHub — é a URL do arquivo manifest.json publicado pela Kontacto no Blob de distribuição, já com a credencial de leitura embutida (termina em algo como \"...manifest.json?sv=...&sig=...\"). Peça esse link pra Kontacto; colar a URL do GitHub aqui não funciona.",
    icon: { lib: "ion", name: "key-outline" },
  },
  {
    titulo: "Pasta do Backend / Pasta do Frontend",
    texto:
      "As pastas NESTA máquina onde o Backend e o Frontend rodando agora ficam — são o que é substituído a cada atualização aplicada. O serviço baixa os dois pacotes (Backend e Frontend) do Blob de distribuição e troca cada um na pasta correspondente.",
    icon: { lib: "ion", name: "folder-outline" },
  },
  {
    titulo: "Intervalo (minutos)",
    texto:
      "De quanto em quanto tempo o sistema verifica sozinho se há uma versão nova. Mínimo de 5 minutos — ou 0 pra desligar a verificação automática (nesse caso, só o botão \"Verificar agora\" checa).",
    icon: { lib: "ion", name: "time-outline" },
  },
  {
    titulo: "Verificar agora",
    texto:
      "Dispara a verificação na hora, sem esperar o próximo ciclo automático — funciona mesmo com o intervalo em 0 (desligado). Só baixa e avisa se houver algo novo, nunca troca a versão em produção sozinho.",
    icon: { lib: "ion", name: "refresh-outline" },
  },
  {
    titulo: "Gravar",
    texto: "Salva a URL do manifest, as pastas e o intervalo. Não baixa nem aplica nada por si só — só grava a configuração.",
    icon: { lib: "ion", name: "checkmark" },
  },
  {
    titulo: "Aplicar agora",
    texto:
      "Só aparece quando já existe uma atualização baixada e pronta. Troca a versão em produção e REINICIA o backend na hora — qualquer pessoa usando o sistema perde a conexão por alguns segundos.",
    icon: { lib: "ion", name: "cloud-download-outline" },
    cor: colors.brandPrimary,
  },
  {
    titulo: "Reverter para versão anterior",
    texto:
      "Volta pra última versão que estava rodando antes da atualização mais recente aplicada, e reinicia o backend do mesmo jeito. Fica disponível sempre que existir uma versão anterior guardada, não só logo depois de atualizar.",
    icon: { lib: "ion", name: "arrow-undo-outline" },
    cor: colors.warning,
  },
];

// Serviço do Sistema (Configurações > Administração, só usuário Master) —
// primeira aba: "Atualização", configura a instalação automática de
// Backend/Frontend a partir do repositório de distribuição da Kontacto.
// Ver PENDENCIAS.md > "Serviço do Sistema — Atualização" pro desenho
// completo. Nasce com o esqueleto de abas já pronto (`TABS`) mesmo só
// tendo uma aba real hoje — outras virão depois, pedido explícito do
// usuário.
//
// Diferente de `modulos-recursos.tsx`/`ia-key.tsx`/`whatsapp-config.tsx`
// (só escondidas no tile de Configurações, sem guard real), esta tela
// bloqueia acesso direto por URL também — "Só o Master terá acesso a essa
// tela" foi pedido explícito, não só "esconder o atalho".

type TabKey = "atualizacao";
const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "atualizacao", label: "Atualização", icon: "cloud-download-outline" },
];

function formatQuando(iso: string | null): string {
  if (!iso) return "nunca";
  try {
    const d = new Date(iso);
    return d.toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

export default function ServicoSistemaScreen() {
  const router = useRouter();
  const { isMaster } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Serviço do Sistema está disponível apenas no web."
        testID="servico-sistema-web-only"
      />
    );
  }
  if (!isMaster) {
    return (
      <LockedView
        title="Acesso restrito"
        message="Serviço do Sistema é uma área exclusiva do usuário master."
        testID="servico-sistema-master-only"
      />
    );
  }

  const f = useServicoSistemaForm();
  const [tab, setTab] = useState<TabKey>("atualizacao");
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const handleSave = async () => {
    await f.save();
  };

  const handleAplicar = () => {
    fb.showConfirm(
      `Aplicar a atualização (commit ${f.form.commit_pendente}) agora? O backend vai reiniciar em instantes — qualquer pessoa usando o sistema perde a conexão por alguns segundos.`,
      () => { void f.aplicar(); },
      { title: "Aplicar atualização", confirmText: "Aplicar agora" },
    );
  };

  const handleReverter = () => {
    fb.showConfirm(
      `Reverter para a versão anterior (commit ${f.form.commit_anterior})? O backend vai reiniciar em instantes — qualquer pessoa usando o sistema perde a conexão por alguns segundos.`,
      () => { void f.reverter(); },
      { title: "Reverter atualização", confirmText: "Reverter", destructive: true },
    );
  };

  if (f.loadingInit) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="servico-sistema-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Serviço do Sistema</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline"
          label="Ajuda"
          onPress={() => setAjudaOpen(true)}
          color={colors.onBrandPrimary}
          style={{ marginRight: spacing.sm }}
          testID="servico-sistema-ajuda"
        />
        <Pressable onPress={handleSave} disabled={f.saving} style={styles.saveBtn} testID="servico-sistema-salvar">
          {f.saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveBtnText}>Gravar</Text>}
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBarScroll} contentContainerStyle={styles.tabBar}>
        {TABS.map((t) => (
          <Pressable
            key={t.key}
            onPress={() => setTab(t.key)}
            style={[styles.tabBtn, tab === t.key && styles.tabBtnActive]}
            testID={`servico-sistema-tab-${t.key}`}
          >
            <Ionicons name={t.icon} size={15} color={tab === t.key ? colors.onBrandPrimary : colors.onSurface} />
            <Text style={[styles.tabBtnText, tab === t.key && styles.tabBtnTextActive]}>{t.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView style={styles.contentScroll} contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={WEB_CONTENT_SHELL}>
          {tab === "atualizacao" ? (
            <>
              <View style={styles.card}>
                <Text style={styles.sectionTitle}>Repositório de distribuição</Text>
                <Text style={styles.helperText}>
                  URL do manifest.json fornecida pela Kontacto (já inclui a credencial de leitura) — é de onde as
                  atualizações de Backend e Frontend são baixadas.
                </Text>
                <Text style={styles.label}>URL do manifest (credencial)</Text>
                <TextInput
                  value={f.form.manifest_url}
                  onChangeText={(v) => f.setField("manifest_url", v)}
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                  placeholder="https://.../manifest.json?sv=...&sig=..."
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="servico-sistema-manifest-url"
                />

                <Text style={styles.sectionTitle}>Pastas locais</Text>
                <Text style={styles.helperText}>
                  Pasta onde os arquivos do Backend/Frontend rodando nesta máquina ficam — é o que é trocado a cada
                  atualização aplicada.
                </Text>
                <Text style={styles.label}>Pasta do Backend</Text>
                <TextInput
                  value={f.form.pasta_backend}
                  onChangeText={(v) => f.setField("pasta_backend", v)}
                  autoCapitalize="none"
                  autoCorrect={false}
                  placeholder="C:\BackOn\current-backend"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="servico-sistema-pasta-backend"
                />
                <Text style={styles.label}>Pasta do Frontend</Text>
                <TextInput
                  value={f.form.pasta_frontend}
                  onChangeText={(v) => f.setField("pasta_frontend", v)}
                  autoCapitalize="none"
                  autoCorrect={false}
                  placeholder="C:\BackOn\current-frontend"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="servico-sistema-pasta-frontend"
                />

                <Text style={styles.sectionTitle}>Verificação automática</Text>
                <Text style={styles.helperText}>
                  A cada quantos minutos o sistema verifica sozinho se há uma atualização nova — quando encontrar, já
                  baixa, mas nunca troca a versão em produção sem você confirmar aqui. Deixe 0 para desligar a
                  verificação automática (aí só o botão "Verificar agora" checa).
                </Text>
                <View style={styles.rowFields}>
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Intervalo (minutos, 0 = desligado)</Text>
                    <TextInput
                      value={f.form.intervalo_minutos}
                      onChangeText={(v) => f.setField("intervalo_minutos", v.replace(/[^0-9]/g, ""))}
                      keyboardType="numeric"
                      style={styles.input}
                      testID="servico-sistema-intervalo"
                    />
                  </View>
                </View>
                <Pressable
                  onPress={() => { void f.verificarAgora(); }}
                  disabled={f.verificando}
                  style={[styles.secondaryBtn, f.verificando && { opacity: 0.7 }]}
                  testID="servico-sistema-verificar-agora"
                >
                  {f.verificando ? (
                    <>
                      <ActivityIndicator color={colors.brandPrimary} size="small" />
                      <Text style={styles.secondaryBtnText}>Verificando…</Text>
                    </>
                  ) : (
                    <Text style={styles.secondaryBtnText}>Verificar agora</Text>
                  )}
                </Pressable>
              </View>

              <View style={styles.card}>
                <Text style={styles.sectionTitle}>Status</Text>
                <View style={styles.statusRow}>
                  <Text style={styles.statusLabel}>Versão atual:</Text>
                  <Text style={styles.statusValue}>{f.form.commit_atual || "—"}</Text>
                </View>
                <View style={styles.statusRow}>
                  <Text style={styles.statusLabel}>Última verificação:</Text>
                  <Text style={styles.statusValue}>{formatQuando(f.form.ultima_verificacao)}</Text>
                </View>
                {f.form.ultimo_erro ? (
                  <View style={styles.statusRow}>
                    <Text style={styles.statusLabel}>Último erro:</Text>
                    <Text style={[styles.statusValue, { color: colors.error }]}>{f.form.ultimo_erro}</Text>
                  </View>
                ) : null}

                {f.form.commit_pendente ? (
                  <View style={styles.destaqueBox}>
                    <Text style={styles.destaqueTitulo}>
                      Atualização disponível (commit {f.form.commit_pendente}) — pronta para aplicar.
                    </Text>
                    <Pressable
                      onPress={handleAplicar}
                      disabled={f.aplicando}
                      style={[styles.primaryBtn, f.aplicando && { opacity: 0.7 }]}
                      testID="servico-sistema-aplicar"
                    >
                      {f.aplicando ? (
                        <>
                          <ActivityIndicator color="#fff" size="small" />
                          <Text style={styles.primaryBtnText}>Aplicando…</Text>
                        </>
                      ) : (
                        <Text style={styles.primaryBtnText}>Aplicar agora</Text>
                      )}
                    </Pressable>
                  </View>
                ) : (
                  <Text style={styles.helperText}>Nenhuma atualização pendente no momento.</Text>
                )}

                {f.form.commit_anterior ? (
                  <View style={{ marginTop: spacing.md }}>
                    <Text style={styles.helperText}>
                      Versão anterior disponível para reverter: {f.form.commit_anterior}.
                    </Text>
                    <Pressable
                      onPress={handleReverter}
                      disabled={f.revertendo}
                      style={[styles.secondaryBtn, f.revertendo && { opacity: 0.7 }]}
                      testID="servico-sistema-reverter"
                    >
                      {f.revertendo ? (
                        <>
                          <ActivityIndicator color={colors.brandPrimary} size="small" />
                          <Text style={styles.secondaryBtnText}>Revertendo…</Text>
                        </>
                      ) : (
                        <Text style={styles.secondaryBtnText}>Reverter para versão anterior</Text>
                      )}
                    </Pressable>
                  </View>
                ) : null}
              </View>
            </>
          ) : null}
        </View>
      </ScrollView>

      <AjudaPedidoModal
        visible={ajudaOpen}
        onClose={() => setAjudaOpen(false)}
        titulo="Serviço do Sistema"
        itens={SERVICO_SISTEMA_AJUDA_ITENS}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  saveBtn: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.onBrandPrimary + "22", minWidth: 40, alignItems: "center" },
  saveBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
  tabBarScroll: { backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, flexGrow: 0 },
  tabBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, gap: spacing.sm, paddingVertical: spacing.sm },
  tabBtn: { flexDirection: "row", alignItems: "center", gap: 6, height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tabBtnActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  tabBtnTextActive: { color: colors.onBrandPrimary },
  contentScroll: { flex: 1 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, alignSelf: "stretch", width: "100%", marginBottom: spacing.md,
  },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.md, marginBottom: spacing.xs, textTransform: "uppercase" },
  helperText: { fontSize: 12, color: colors.muted, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs, marginBottom: 3 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 0, height: 36, fontSize: 13, lineHeight: 16,
    color: colors.onSurface, textAlignVertical: "center",
  },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colNarrow: { width: 140 },
  statusRow: { flexDirection: "row", gap: spacing.xs, marginBottom: 4 },
  statusLabel: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  statusValue: { fontSize: 12, color: colors.onSurface },
  destaqueBox: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary,
    padding: spacing.sm, marginTop: spacing.sm, gap: spacing.sm,
  },
  destaqueTitulo: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    alignSelf: "flex-start", backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingVertical: 9, paddingHorizontal: spacing.lg,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    alignSelf: "flex-start", borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingVertical: 9, paddingHorizontal: spacing.lg, marginTop: spacing.xs,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
});
