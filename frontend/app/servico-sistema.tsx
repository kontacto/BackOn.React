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
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { useServicoSistemaForm } from "@/src/hooks/useServicoSistemaForm";
import { useBackupSistemaForm } from "@/src/hooks/useBackupSistemaForm";
import BackupLogsModal from "@/src/components/BackupLogsModal";
import IndicesNaoUsadosModal from "@/src/components/IndicesNaoUsadosModal";
import SelectField from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
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
    titulo: "Canal — Homologação ou Produção",
    texto:
      "Homologação (equipe): baixa toda versão publicada, mesmo ainda em teste — e só pode ser aplicada aqui nesta tela, pelo botão \"Aplicar agora\" abaixo. Produção (clientes): só baixa versões já marcadas como estáveis pela equipe — e só pode ser aplicada pelo botão \"Atualizar Sistema\" no menu lateral (visível só quando há algo pendente, pra Supervisor/Gerente/Master). Cada canal tem exatamente 1 jeito de aplicar — nunca os dois ao mesmo tempo.",
    icon: { lib: "ion", name: "git-branch-outline" },
  },
  {
    titulo: "Cel Suporte (Apoio Fiscal BackOn)",
    texto:
      "Número de WhatsApp do SUPORTE da Kontacto — quando preenchido, toda rejeição fiscal (NFC-e/NF-e/NFS-e/Cancelamento) nesta instalação dispara automaticamente um aviso por WhatsApp pra esse número, além do e-mail que já vai sempre pra suporte@kontacto.com.br. Não é o WhatsApp do cliente/lojista — é o canal interno da equipe de suporte.",
    icon: { lib: "ion", name: "logo-whatsapp" },
  },
  {
    titulo: "Manutenção Automática de Índices",
    texto:
      "Reconstrói sozinho, de tempos em tempos, os índices do banco que ficam \"desorganizados\" com o uso — sem isso, o sistema pode ficar lento ou até travar em algumas operações depois de meses de uso. Roda só nos dias/hora que você escolher (prefira madrugada, sem ninguém usando o sistema, porque a operação pode travar a tela por alguns minutos enquanto roda) e no máximo 1 vez por dia. Desligue só se este cliente já tiver sua própria rotina de manutenção de banco.",
    icon: { lib: "ion", name: "build-outline" },
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
  {
    titulo: "Orçamento de Tempo / Rodar agora / Índices Não Utilizados",
    texto:
      "\"Orçamento de tempo\" limita quantos minutos a manutenção pode gastar reconstruindo índices numa madrugada — se o banco tiver muita coisa fragmentada, o que sobrar fica pro próximo dia agendado, em vez de invadir o horário de expediente com a tela travada. \"Rodar agora\" força uma manutenção completa na hora, fora da janela agendada — útil pra testar, mas pode travar a tela por um tempo. \"Índices Não Utilizados\" é só um relatório (nada é apagado sozinho) dos índices que ninguém usou desde a última vez que o banco reiniciou — revise com calma antes de decidir remover algum, um índice usado só 1x por mês pode aparecer aqui sem ser realmente inútil.",
    icon: { lib: "ion", name: "speedometer-outline" },
  },
  {
    titulo: "Verificação de Integridade (DBCC CHECKDB)",
    texto:
      "Confere se o banco tem alguma página de dados corrompida — diferente da Manutenção de Índices (que só organiza, não detecta corrupção). É mais pesada, por isso roda com menos frequência (o padrão é 1x por semana, aos domingos de madrugada). Se encontrar algo, o resultado fica registrado abaixo e o suporte técnico deve ser acionado.",
    icon: { lib: "ion", name: "shield-checkmark-outline" },
  },
  {
    titulo: "Espaço do Banco",
    texto:
      "Só aparece em instalações que usam a versão gratuita (Express) do SQL Server, que tem um limite rígido de 10GB de dados por banco — passar desse limite trava novos lançamentos até liberar espaço ou trocar de versão do banco. Este indicador mostra o quanto já foi usado desse limite, atualizado automaticamente.",
    icon: { lib: "ion", name: "server-outline" },
  },
  {
    titulo: "Backup Programado",
    texto:
      "Faz backup do banco de dados sozinho, nos dias/horário que você escolher, repetindo a cada X horas dentro do dia (ex.: a partir das 22h, a cada 6h). O destino pode ser uma pasta no PRÓPRIO servidor do banco (não é a pasta desta máquina que roda o app) ou a Nuvem (Blob) já configurada em Controle do Sistema. Backups antigos (mais velhos que a Retenção configurada) são apagados automaticamente, pra não acumular pra sempre.",
    icon: { lib: "ion", name: "save-outline" },
  },
  {
    titulo: "Fazer backup agora / Ver Logs de Backup",
    texto:
      "\"Fazer backup agora\" dispara um backup na hora, sem esperar o próximo horário programado. \"Ver Logs de Backup\" mostra o histórico de execuções — sucesso ou erro, tamanho do arquivo, quanto tempo levou.",
    icon: { lib: "ion", name: "cloud-upload-outline" },
  },
];

// Mesma convenção 0=domingo..6=sábado já usada em "Dias da Semana (Web
// Convidado)" (produto-completo.tsx) — mesmo rótulo/ordem.
const DIAS_SEMANA_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

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

type TabKey = "atualizacao" | "backup";
const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "atualizacao", label: "Atualização", icon: "cloud-download-outline" },
  { key: "backup", label: "Backup", icon: "save-outline" },
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
  const b = useBackupSistemaForm(f.conn);
  const [tab, setTab] = useState<TabKey>("atualizacao");
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [backupLogsOpen, setBackupLogsOpen] = useState(false);
  const [indicesNaoUsadosOpen, setIndicesNaoUsadosOpen] = useState(false);

  const handleSave = async () => {
    if (tab === "backup") { await b.save(); return; }
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
        <Pressable
          onPress={handleSave}
          disabled={tab === "backup" ? b.saving : f.saving}
          style={styles.saveBtn}
          testID="servico-sistema-salvar"
        >
          {(tab === "backup" ? b.saving : f.saving) ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.saveBtnText}>Gravar</Text>
          )}
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
                <AccordionSection title="Repositório de Distribuição" defaultExpanded testID="servico-sistema-acc-repositorio">
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
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Pastas Locais" testID="servico-sistema-acc-pastas">
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
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Canal" testID="servico-sistema-acc-canal">
                  <Text style={styles.helperText}>
                    Homologação (equipe): recebe toda versão publicada e só é aplicada por esta tela. Produção
                    (clientes): só recebe versões já marcadas como estáveis, e só é aplicada pelo botão "Atualizar
                    Sistema" no menu lateral.
                  </Text>
                  <View style={styles.rowFields}>
                    <View style={styles.colCombo}>
                      <SelectField
                        value={f.form.canal}
                        onChange={(v) => f.setField("canal", v === "P" ? "P" : "H")}
                        options={[
                          { value: "H", label: "Homologação (equipe)" },
                          { value: "P", label: "Produção (clientes)" },
                        ]}
                        compactWeb
                        testID="servico-sistema-canal"
                      />
                    </View>
                  </View>
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Apoio Fiscal BackOn — Cel Suporte" testID="servico-sistema-acc-cel-suporte">
                  <Text style={styles.helperText}>
                    Número de WhatsApp do SUPORTE da Kontacto (não do cliente) — recebe uma notificação automática
                    sempre que uma nota fiscal for rejeitada nesta instalação, além do e-mail já enviado pra
                    suporte@kontacto.com.br. Deixe em branco para receber só por e-mail.
                  </Text>
                  <View style={styles.rowFields}>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Cel Suporte (WhatsApp)</Text>
                      <TextInput
                        value={f.form.cel_suporte}
                        onChangeText={(v) => f.setField("cel_suporte", v)}
                        keyboardType="phone-pad"
                        placeholder="(11) 91234-5678"
                        placeholderTextColor={colors.muted}
                        style={styles.input}
                        testID="servico-sistema-cel-suporte"
                      />
                    </View>
                  </View>
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Verificação Automática" testID="servico-sistema-acc-verificacao">
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
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Manutenção Automática de Índices" testID="servico-sistema-acc-manutencao">
                  <Text style={styles.helperText}>
                    Reconstrói sozinho os índices do banco de tempos em tempos, pra evitar lentidão/travamento com o uso
                    ao longo dos meses. Escolha uma janela de baixo uso (madrugada) — a operação pode travar a tela
                    brevemente enquanto roda.
                  </Text>
                  <Pressable
                    onPress={() => f.setField("manutencao_indices_ativo", !f.form.manutencao_indices_ativo)}
                    style={styles.checkboxRow}
                    testID="servico-sistema-manutencao-ativo"
                  >
                    <Ionicons
                      name={f.form.manutencao_indices_ativo ? "checkbox" : "square-outline"}
                      size={18}
                      color={f.form.manutencao_indices_ativo ? colors.brandPrimary : colors.muted}
                    />
                    <Text style={styles.checkboxLabel}>Manutenção automática ativa</Text>
                  </Pressable>
                  <Text style={styles.label}>Dias da Semana</Text>
                  <View style={styles.chipsRow}>
                    {DIAS_SEMANA_LABELS.map((diaLabel, i) => {
                      const d = String(i);
                      const diasAtuais = f.form.manutencao_indices_dias_semana.split(",").filter(Boolean);
                      const sel = diasAtuais.includes(d);
                      const toggleDia = () => {
                        const novos = sel ? diasAtuais.filter((x) => x !== d) : [...diasAtuais, d];
                        f.setField("manutencao_indices_dias_semana", novos.sort().join(","));
                      };
                      return (
                        <Pressable
                          key={d}
                          onPress={toggleDia}
                          style={[styles.chip, sel && styles.chipSel]}
                          testID={`servico-sistema-manutencao-dia-${d}`}
                        >
                          <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{diaLabel}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  <View style={styles.rowFields}>
                    <View style={[styles.colNarrow, { width: 120 }]}>
                      <Text style={styles.label}>Hora</Text>
                      <WebDateField
                        value={f.form.manutencao_indices_hora}
                        onChange={(v) => f.setField("manutencao_indices_hora", v || "03:00")}
                        type="time"
                        testID="servico-sistema-manutencao-hora"
                      />
                    </View>
                    <View style={[styles.colNarrow, { width: 160 }]}>
                      <Text style={styles.label}>Orçamento de Tempo (min)</Text>
                      <TextInput
                        value={f.form.manutencao_indices_orcamento_minutos}
                        onChangeText={(v) => f.setField("manutencao_indices_orcamento_minutos", v.replace(/[^0-9]/g, ""))}
                        keyboardType="numeric"
                        style={styles.input}
                        testID="servico-sistema-manutencao-orcamento"
                      />
                    </View>
                  </View>

                  <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginTop: spacing.sm }}>
                    <Pressable
                      onPress={() => { void f.rodarManutencaoAgora(); }}
                      disabled={f.rodandoManutencao}
                      style={[styles.secondaryBtn, { marginTop: 0 }, f.rodandoManutencao && { opacity: 0.7 }]}
                      testID="servico-sistema-manutencao-rodar-agora"
                    >
                      {f.rodandoManutencao ? (
                        <>
                          <ActivityIndicator color={colors.brandPrimary} size="small" />
                          <Text style={styles.secondaryBtnText}>Rodando…</Text>
                        </>
                      ) : (
                        <Text style={styles.secondaryBtnText}>Rodar agora</Text>
                      )}
                    </Pressable>
                    <Pressable
                      onPress={() => setIndicesNaoUsadosOpen(true)}
                      style={[styles.secondaryBtn, { marginTop: 0 }]}
                      testID="servico-sistema-manutencao-ver-nao-usados"
                    >
                      <Text style={styles.secondaryBtnText}>Índices Não Utilizados</Text>
                    </Pressable>
                  </View>

                  <View style={{ marginTop: spacing.md }}>
                    <View style={styles.statusRow}>
                      <Text style={styles.statusLabel}>Última execução:</Text>
                      <Text style={styles.statusValue}>{formatQuando(f.form.manutencao_indices_ultima_execucao)}</Text>
                    </View>
                    {f.form.manutencao_indices_ultimo_resultado ? (
                      <View style={styles.statusRow}>
                        <Text style={styles.statusLabel}>Último resultado:</Text>
                        <Text style={styles.statusValue}>{f.form.manutencao_indices_ultimo_resultado}</Text>
                      </View>
                    ) : null}
                  </View>
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Verificação de Integridade (DBCC CHECKDB)" testID="servico-sistema-acc-checkdb">
                  <Text style={styles.helperText}>
                    Confere se o banco tem alguma página de dados corrompida — mais pesada que a Manutenção de
                    Índices, por isso o padrão é rodar só 1 vez por semana.
                  </Text>
                  <Pressable
                    onPress={() => f.setField("checkdb_ativo", !f.form.checkdb_ativo)}
                    style={styles.checkboxRow}
                    testID="servico-sistema-checkdb-ativo"
                  >
                    <Ionicons
                      name={f.form.checkdb_ativo ? "checkbox" : "square-outline"}
                      size={18}
                      color={f.form.checkdb_ativo ? colors.brandPrimary : colors.muted}
                    />
                    <Text style={styles.checkboxLabel}>Verificação automática ativa</Text>
                  </Pressable>
                  <Text style={styles.label}>Dias da Semana</Text>
                  <View style={styles.chipsRow}>
                    {DIAS_SEMANA_LABELS.map((diaLabel, i) => {
                      const d = String(i);
                      const diasAtuais = f.form.checkdb_dias_semana.split(",").filter(Boolean);
                      const sel = diasAtuais.includes(d);
                      const toggleDia = () => {
                        const novos = sel ? diasAtuais.filter((x) => x !== d) : [...diasAtuais, d];
                        f.setField("checkdb_dias_semana", novos.sort().join(","));
                      };
                      return (
                        <Pressable
                          key={d}
                          onPress={toggleDia}
                          style={[styles.chip, sel && styles.chipSel]}
                          testID={`servico-sistema-checkdb-dia-${d}`}
                        >
                          <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{diaLabel}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  <View style={styles.rowFields}>
                    <View style={[styles.colNarrow, { width: 120 }]}>
                      <Text style={styles.label}>Hora</Text>
                      <WebDateField
                        value={f.form.checkdb_hora}
                        onChange={(v) => f.setField("checkdb_hora", v || "04:00")}
                        type="time"
                        testID="servico-sistema-checkdb-hora"
                      />
                    </View>
                  </View>
                  <View style={{ marginTop: spacing.md }}>
                    <View style={styles.statusRow}>
                      <Text style={styles.statusLabel}>Última execução:</Text>
                      <Text style={styles.statusValue}>{formatQuando(f.form.checkdb_ultima_execucao)}</Text>
                    </View>
                    {f.form.checkdb_ultimo_resultado ? (
                      <View style={styles.statusRow}>
                        <Text style={styles.statusLabel}>Último resultado:</Text>
                        <Text
                          style={[
                            styles.statusValue,
                            f.form.checkdb_ultimo_resultado.toLowerCase().includes("possível problema") && { color: colors.error },
                          ]}
                        >
                          {f.form.checkdb_ultimo_resultado}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                </AccordionSection>
              </View>

              {f.form.espaco_pct_usado != null ? (
                <View style={styles.card}>
                  <AccordionSection title="Espaço do Banco (SQL Server Express)" testID="servico-sistema-acc-espaco">
                    <Text style={styles.helperText}>
                      A versão Express do SQL Server tem um limite rígido de 10GB de dados por banco — passar desse
                      limite trava novos lançamentos.
                    </Text>
                    <View style={styles.statusRow}>
                      <Text style={styles.statusLabel}>Uso atual:</Text>
                      <Text
                        style={[
                          styles.statusValue,
                          { fontWeight: "700" },
                          f.form.espaco_pct_usado >= 80 && { color: colors.error },
                        ]}
                      >
                        {f.form.espaco_pct_usado.toFixed(1)}% de 10GB
                      </Text>
                    </View>
                    <View style={styles.statusRow}>
                      <Text style={styles.statusLabel}>Verificado em:</Text>
                      <Text style={styles.statusValue}>{formatQuando(f.form.espaco_verificado_em)}</Text>
                    </View>
                  </AccordionSection>
                </View>
              ) : null}

              <View style={styles.card}>
                <AccordionSection title="Status" defaultExpanded testID="servico-sistema-acc-status">
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
                    {f.form.canal === "P" ? (
                      <Text style={styles.helperText}>
                        Canal Produção — esta atualização é aplicada pelo botão "Atualizar Sistema" no menu
                        lateral (visível pra Supervisor/Gerente/Master), não por aqui.
                      </Text>
                    ) : (
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
                    )}
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
                </AccordionSection>
              </View>
            </>
          ) : null}

          {tab === "backup" ? (
            <>
              <View style={styles.card}>
                <AccordionSection title="Agendamento" defaultExpanded testID="servico-sistema-acc-backup-agendamento">
                  <Text style={styles.helperText}>
                    Faz backup do banco sozinho, nos dias/horário escolhidos, repetindo a cada X horas dentro do dia.
                    Prefira uma janela de baixo uso — a operação consome recursos do servidor enquanto roda.
                  </Text>
                  <Pressable
                    onPress={() => b.setField("ativo", !b.form.ativo)}
                    style={styles.checkboxRow}
                    testID="servico-sistema-backup-ativo"
                  >
                    <Ionicons
                      name={b.form.ativo ? "checkbox" : "square-outline"}
                      size={18}
                      color={b.form.ativo ? colors.brandPrimary : colors.muted}
                    />
                    <Text style={styles.checkboxLabel}>Backup automático ativo</Text>
                  </Pressable>

                  <Text style={styles.label}>Dias da Semana</Text>
                  <View style={styles.chipsRow}>
                    {DIAS_SEMANA_LABELS.map((diaLabel, i) => {
                      const d = String(i);
                      const diasAtuais = b.form.dias_semana.split(",").filter(Boolean);
                      const sel = diasAtuais.includes(d);
                      const toggleDia = () => {
                        const novos = sel ? diasAtuais.filter((x) => x !== d) : [...diasAtuais, d];
                        b.setField("dias_semana", novos.sort().join(","));
                      };
                      return (
                        <Pressable
                          key={d}
                          onPress={toggleDia}
                          style={[styles.chip, sel && styles.chipSel]}
                          testID={`servico-sistema-backup-dia-${d}`}
                        >
                          <Text style={[styles.chipText, sel && { color: colors.onBrandPrimary }]}>{diaLabel}</Text>
                        </Pressable>
                      );
                    })}
                  </View>

                  <View style={styles.rowFields}>
                    <View style={[styles.colNarrow, { width: 120 }]}>
                      <Text style={styles.label}>Hora de Início</Text>
                      <WebDateField
                        value={b.form.hora_inicio}
                        onChange={(v) => b.setField("hora_inicio", v || "02:00")}
                        type="time"
                        testID="servico-sistema-backup-hora"
                      />
                    </View>
                    <View style={[styles.colNarrow, { width: 140 }]}>
                      <Text style={styles.label}>Intervalo (horas)</Text>
                      <TextInput
                        value={b.form.intervalo_horas}
                        onChangeText={(v) => b.setField("intervalo_horas", v.replace(/[^0-9]/g, ""))}
                        keyboardType="numeric"
                        style={styles.input}
                        testID="servico-sistema-backup-intervalo"
                      />
                    </View>
                    <View style={[styles.colNarrow, { width: 140 }]}>
                      <Text style={styles.label}>Retenção (dias)</Text>
                      <TextInput
                        value={b.form.retencao_dias}
                        onChangeText={(v) => b.setField("retencao_dias", v.replace(/[^0-9]/g, ""))}
                        keyboardType="numeric"
                        style={styles.input}
                        testID="servico-sistema-backup-retencao"
                      />
                    </View>
                  </View>
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Destino" defaultExpanded testID="servico-sistema-acc-backup-destino">
                  <View style={styles.rowFields}>
                    <View style={styles.colCombo}>
                      <SelectField
                        value={b.form.destino}
                        onChange={(v) => b.setField("destino", v === "BLOB" ? "BLOB" : "LOCAL")}
                        options={[
                          { value: "LOCAL", label: "Local (pasta no servidor)" },
                          { value: "BLOB", label: "Nuvem (Blob)" },
                        ]}
                        compactWeb
                        testID="servico-sistema-backup-destino"
                      />
                    </View>
                  </View>
                  {b.form.destino === "LOCAL" ? (
                    <>
                      <Text style={styles.helperText}>
                        Pasta no servidor onde o SQL Server roda — não é a pasta desta máquina que abre o app.
                      </Text>
                      <Text style={styles.label}>Pasta de Destino</Text>
                      <TextInput
                        value={b.form.pasta_local}
                        onChangeText={(v) => b.setField("pasta_local", v)}
                        autoCapitalize="none"
                        autoCorrect={false}
                        placeholder="C:\Backups\SQL"
                        placeholderTextColor={colors.muted}
                        style={styles.input}
                        testID="servico-sistema-backup-pasta"
                      />
                    </>
                  ) : (
                    <>
                      <Text style={styles.helperText}>
                        Usa a mesma credencial de Blob já configurada em Controle do Sistema. Nome do container abaixo
                        (criado automaticamente se ainda não existir).
                      </Text>
                      <Text style={styles.label}>Container do Blob</Text>
                      <TextInput
                        value={b.form.blob_container}
                        onChangeText={(v) => b.setField("blob_container", v)}
                        autoCapitalize="none"
                        autoCorrect={false}
                        style={styles.input}
                        testID="servico-sistema-backup-container"
                      />
                    </>
                  )}
                </AccordionSection>
              </View>

              <View style={styles.card}>
                <AccordionSection title="Ações e Status" defaultExpanded testID="servico-sistema-acc-backup-status">
                  <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                    <Pressable
                      onPress={() => { void b.executarAgora(); }}
                      disabled={b.executando}
                      style={[styles.secondaryBtn, { marginTop: 0 }, b.executando && { opacity: 0.7 }]}
                      testID="servico-sistema-backup-executar"
                    >
                      {b.executando ? (
                        <>
                          <ActivityIndicator color={colors.brandPrimary} size="small" />
                          <Text style={styles.secondaryBtnText}>Fazendo backup…</Text>
                        </>
                      ) : (
                        <Text style={styles.secondaryBtnText}>Fazer backup agora</Text>
                      )}
                    </Pressable>
                    <Pressable
                      onPress={() => setBackupLogsOpen(true)}
                      style={[styles.secondaryBtn, { marginTop: 0 }]}
                      testID="servico-sistema-backup-ver-logs"
                    >
                      <Text style={styles.secondaryBtnText}>Ver Logs de Backup</Text>
                    </Pressable>
                  </View>

                  <View style={{ marginTop: spacing.md }}>
                    <View style={styles.statusRow}>
                      <Text style={styles.statusLabel}>Última execução:</Text>
                      <Text style={styles.statusValue}>{formatQuando(b.form.ultima_execucao)}</Text>
                    </View>
                    {b.form.ultimo_resultado ? (
                      <View style={styles.statusRow}>
                        <Text style={styles.statusLabel}>Último resultado:</Text>
                        <Text style={styles.statusValue}>{b.form.ultimo_resultado}</Text>
                      </View>
                    ) : null}
                  </View>
                </AccordionSection>
              </View>
            </>
          ) : null}
        </View>
      </ScrollView>

      <BackupLogsModal
        visible={backupLogsOpen}
        onClose={() => setBackupLogsOpen(false)}
        onLoad={b.carregarLogs}
      />

      <IndicesNaoUsadosModal
        visible={indicesNaoUsadosOpen}
        onClose={() => setIndicesNaoUsadosOpen(false)}
        onLoad={f.buscarIndicesNaoUsados}
      />

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
  colCombo: { width: 260 },
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
  checkboxRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm, marginBottom: spacing.xs, alignSelf: "flex-start" },
  checkboxLabel: { fontSize: 13, color: colors.onSurface },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: spacing.sm },
  chip: { paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
});
