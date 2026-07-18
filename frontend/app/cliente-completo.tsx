import { useState } from "react";
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import SelectField from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import { colors, radius, spacing } from "@/src/theme/colors";
import {
  WEB_CONTENT_SHELL,
  WEB_FILTER_CARD,
  WEB_SCROLL_CENTER,
} from "@/src/theme/webLayout";
import { useClienteForm, ENDERECO_TIPOS, toastBackgroundColor } from "@/src/hooks/useClienteForm";

const TOAST_SHADOW_STYLE = { boxShadow: "0 6px 12px rgba(0, 0, 0, 0.35)" };

type TabKey = "principais" | "secundarios" | "contatos" | "anexos";

const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "principais", label: "Dados Principais", icon: "person-outline" },
  { key: "secundarios", label: "Dados Secundários", icon: "briefcase-outline" },
  { key: "contatos", label: "Contatos", icon: "people-outline" },
  { key: "anexos", label: "Anexos", icon: "attach-outline" },
];

// Itens do legado (frmmanclie.frm) que ficam para uma próxima iteração — dependem de
// infraestrutura própria (upload/webcam, ano-exercício, sub-tela dedicada).
// Ver CLAUDE.md > "Legacy field-to-tab mapping" para a lista completa e as tabelas de origem.
const SECUNDARIOS_EM_BREVE = [
  "Tabela de preço por produto do cliente (tabela_cliente / tabela_preco_ajuste)",
  "Conta contábil de transferência (Plano_<ano_exercicio>, ano-a-ano)",
];

// CRT — Código de Regime Tributário (tabela padrão da NF-e, não é lookup do banco).
const CRT_OPTIONS = [
  { value: "1", label: "1 — Simples Nacional" },
  { value: "2", label: "2 — Simples Nacional (excesso sublimite)" },
  { value: "3", label: "3 — Regime Normal" },
];

// Indicador de Presença — tabela padrão da NF-e/NFC-e (não é lookup do banco).
const INDPRES_OPTIONS = [
  { value: "0", label: "0 — Não se aplica" },
  { value: "1", label: "1 — Presencial" },
  { value: "2", label: "2 — Internet" },
  { value: "3", label: "3 — Teleatendimento" },
  { value: "4", label: "4 — NFC-e entrega domicílio" },
  { value: "5", label: "5 — Presencial fora do estabelecimento" },
  { value: "9", label: "9 — Outros" },
];

// ============================================================
// Tela — Cadastro completo de cliente (web-only)
// CRUD estruturado em abas (Dados Principais / Dados Secundários / Contatos),
// inspirado no layout legado (frmmanclie.frm). Complementa o cadastro rápido
// em cliente-form.tsx.
// ============================================================
export default function ClienteCompletoScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="O Cadastro completo de cliente está disponível apenas no web. Use o cadastro rápido pelo app."
        testID="cliente-completo-web-only"
      />
    );
  }

  return <ClienteCompletoWebScreen router={router} can={can} />;
}

function ClienteCompletoWebScreen({
  router,
  can,
}: {
  router: ReturnType<typeof useRouter>;
  can: (perm: string) => boolean;
}) {
  const params = useLocalSearchParams<{ codigo?: string; initial_nome?: string; initial_cgc_cpf?: string }>();
  const editing = !!params.codigo;
  const codigo = params.codigo ? parseInt(String(params.codigo), 10) : null;
  const [tab, setTab] = useState<TabKey>("principais");

  const f = useClienteForm({
    editing,
    codigo,
    initialNome: params.initial_nome ? String(params.initial_nome) : undefined,
    initialCgcCpf: params.initial_cgc_cpf ? String(params.initial_cgc_cpf) : undefined,
    selfRoute: "/cliente-completo",
  });

  // Botão "Ver Contatos" ao lado de Histórico — pedido explícito do usuário
  // (2026-07-12): chama todos os registros da tela Contatos (tabela
  // `contatos`, cadastro/consulta de contatos-lead) já feitos com este
  // cliente. Não confundir com a aba "Contatos" mais abaixo (tabela
  // `cliente_contato` — pessoas de contato da empresa, entidade
  // diferente). `contatos.cliente` é texto livre (nome), não FK — busca
  // por LIKE no nome atual do cliente.
  const [contatosHistOpen, setContatosHistOpen] = useState(false);
  const [contatosHistLoading, setContatosHistLoading] = useState(false);
  const [contatosHist, setContatosHist] = useState<Array<{
    codigo: number; data: string | null; contato: string; profissional_nome: string | null;
    tipo_cliente_nome: string | null; obs: string; data_prev: string | null;
  }>>([]);

  const abrirContatosDoCliente = async () => {
    setContatosHistOpen(true);
    if (!f.conn || !f.nome.trim()) return;
    setContatosHistLoading(true);
    try {
      const base = f.conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(f.conn.servidor)}&banco=${encodeURIComponent(f.conn.banco)}&cliente=${encodeURIComponent(f.nome.trim())}`;
      const r = await fetch(`${base}/api/contatos?${qs}`);
      const j = await r.json();
      setContatosHist(j?.success ? j.items || [] : []);
    } catch { setContatosHist([]); } finally { setContatosHistLoading(false); }
  };

  const isoToBR = (iso: string | null) => {
    if (!iso) return "-";
    const [y, m, d] = iso.split("-");
    return d && m && y ? `${d}/${m}/${y}` : iso;
  };

  if (f.loadingInit) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cliente-completo-screen">
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="cliente-completo-back-button"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Cliente #${codigo} — Cadastro Completo` : "Novo Cliente — Cadastro Completo"}
        </Text>
        {can("CLIENTE.GRAVAR") ? (
          <Pressable
            onPress={() =>
              f.handleSave((novoCodigo, wasEditing) => {
                if (!wasEditing && novoCodigo) {
                  // Cliente novo: fica na tela (não volta pra lista),
                  // recarrega em modo edição pra destravar Telefones/
                  // Endereços/Contatos/Anexos.
                  router.replace({ pathname: "/cliente-completo", params: { codigo: String(novoCodigo) } } as never);
                } else {
                  router.back();
                }
              })
            }
            disabled={f.saving}
            style={({ pressed }) => [styles.saveBtn, (pressed || f.saving) && { opacity: 0.7 }]}
            hitSlop={8}
            testID="cliente-completo-save-button"
          >
            {f.saving ? (
              <ActivityIndicator color={colors.onBrandPrimary} size="small" />
            ) : (
              <>
                <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.saveLabel}>Gravar</Text>
              </>
            )}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {/* ============ Identidade — sempre visível, qualquer aba ============
              Mesmo padrão do Cadastro de Produtos (FrmManPec.frm legado):
              os campos que identificam QUEM é o registro ficam ACIMA da
              barra de abas, nunca escondidos ao trocar de aba. Ver
              CLAUDE.md > "Produto Completo" / decisão do usuário 2026-07-14. */}
          <View style={styles.card} testID="cliente-completo-identidade">
            <View style={styles.formGrid}>
              <Field
                label={`CGC/CPF ${f.docType === "UNKNOWN" ? "" : `(${f.docType})`}${f.exigeCpfCliente ? " *" : ""}`}
                style={styles.colHalf}
              >
                <TextInput
                  value={f.cgcCpf}
                  onChangeText={f.handleCgcCpfChange}
                  onBlur={f.buscarPorCgc}
                  placeholder="CPF (11) ou CNPJ (14, aceita letras)"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, f.cgcCpfError && styles.inputError]}
                  autoCapitalize="characters"
                  testID="cliente-completo-cgc-cpf-input"
                />
                {f.cgcCpfError ? (
                  <Text style={styles.errorText} testID="cliente-completo-cgc-cpf-error">
                    {f.cgcCpfError}
                  </Text>
                ) : null}
              </Field>

              <Field label="Nome / Razão Social *" style={styles.colHalf}>
                <TextInput
                  value={f.nome}
                  onChangeText={f.setNome}
                  placeholder="Nome do cliente"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  maxLength={60}
                  testID="cliente-completo-nome-input"
                />
              </Field>
            </View>
          </View>

          {/* ============ Abas ============ */}
          <View style={styles.tabBar}>
            {TABS.filter((t) => (t.key !== "anexos" && t.key !== "contatos") || codigo != null).map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable
                  key={t.key}
                  onPress={() => setTab(t.key)}
                  style={({ pressed }) => [styles.tabBtn, sel && styles.tabBtnSel, pressed && { opacity: 0.85 }]}
                  testID={`cliente-completo-tab-${t.key}`}
                >
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {/* ============ Dados Principais ============ */}
          {tab === "principais" ? (
            <>
              <View style={styles.card} testID="cliente-completo-tab-content-principais">
                <View style={styles.formGrid}>
                  <Field label="Nome Fantasia" style={styles.colHalf}>
                    <TextInput
                      value={f.nomeFantasia}
                      onChangeText={f.setNomeFantasia}
                      placeholder="Nome fantasia"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      maxLength={50}
                      testID="cliente-completo-nome-fantasia-input"
                    />
                  </Field>

                  <Field label="E-mail" style={styles.colHalf}>
                    <View style={styles.emailRow}>
                      <TextInput
                        value={f.email}
                        onChangeText={f.setEmail}
                        placeholder="email@dominio.com"
                        placeholderTextColor={colors.muted}
                        style={[styles.input, { flex: 1 }]}
                        keyboardType="email-address"
                        autoCapitalize="none"
                        testID="cliente-completo-email-input"
                      />
                      <View style={styles.emailSwitchInline}>
                        <Text style={styles.emailSwitchLabel}>Aceita e-mail</Text>
                        <Switch
                          value={f.aceitaEmail}
                          onValueChange={f.setAceitaEmail}
                          trackColor={{ false: colors.border, true: colors.brandSecondary }}
                          thumbColor={f.aceitaEmail ? colors.brandPrimary : "#f4f3f4"}
                          testID="cliente-completo-aceita-email-switch"
                        />
                      </View>
                    </View>
                  </Field>

                  <Field label={f.labelInscre} style={styles.colHalf}>
                    <TextInput
                      value={f.inscre}
                      onChangeText={f.setInscre}
                      placeholder={f.labelInscre}
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      maxLength={18}
                      testID="cliente-completo-inscre-input"
                    />
                  </Field>

                  {f.docType === "CPF" ? (
                    <Field label="Sexo" style={styles.colHalf}>
                      <View style={styles.radioRow}>
                        {[
                          { value: "M", label: "Masculino" },
                          { value: "F", label: "Feminino" },
                        ].map((opt) => {
                          const sel = f.sexo === opt.value;
                          return (
                            <Pressable
                              key={opt.value}
                              onPress={() => f.setSexo(opt.value)}
                              style={({ pressed }) => [
                                styles.radioBtn,
                                sel && styles.radioBtnSel,
                                pressed && { opacity: 0.8 },
                              ]}
                              testID={`cliente-completo-sexo-${opt.value}`}
                            >
                              <View style={[styles.radioCircle, sel && styles.radioCircleSel]}>
                                {sel ? <View style={styles.radioDot} /> : null}
                              </View>
                              <Text style={[styles.radioLabel, sel && { color: colors.brandPrimary }]}>
                                {opt.label}
                              </Text>
                            </Pressable>
                          );
                        })}
                      </View>
                    </Field>
                  ) : null}

                  <Field label={f.docType === "CNPJ" ? "Data Abertura" : "Data Nascimento"} style={styles.colHalf}>
                    <DateField
                      value={f.dataNasc}
                      onChange={f.setDataNasc}
                      testID="cliente-completo-data-nasc"
                    />
                  </Field>

                  {f.docType === "CNPJ" ? (
                    <Field label="Insc. Municipal" style={styles.colHalf}>
                      <TextInput
                        value={f.inscrMun}
                        onChangeText={f.setInscrMun}
                        placeholder="Inscrição Municipal"
                        placeholderTextColor={colors.muted}
                        style={styles.input}
                        maxLength={18}
                        testID="cliente-completo-inscr-mun-input"
                      />
                    </Field>
                  ) : null}

                  <Field label="Site" style={styles.colHalf}>
                    <TextInput
                      value={f.site}
                      onChangeText={f.setSite}
                      placeholder="www.dominio.com.br"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      autoCapitalize="none"
                      maxLength={60}
                      testID="cliente-completo-site-input"
                    />
                  </Field>

                  <Field label="Situação" style={styles.colHalf}>
                    <View style={styles.radioRow}>
                      {[
                        { value: "A" as const, label: "Ativo" },
                        { value: "I" as const, label: "Inativo" },
                      ].map((opt) => {
                        const sel = f.situacao === opt.value;
                        return (
                          <Pressable
                            key={opt.value}
                            onPress={() => f.setSituacao(opt.value)}
                            style={({ pressed }) => [
                              styles.radioBtn,
                              sel && styles.radioBtnSel,
                              pressed && { opacity: 0.8 },
                            ]}
                            testID={`cliente-completo-situacao-${opt.value}`}
                          >
                            <View style={[styles.radioCircle, sel && styles.radioCircleSel]}>
                              {sel ? <View style={styles.radioDot} /> : null}
                            </View>
                            <Text style={[styles.radioLabel, sel && { color: colors.brandPrimary }]}>
                              {opt.label}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </Field>

                  {f.situacao === "I" ? (
                    <Field label="Inativo em" style={styles.colHalf}>
                      <DateField
                        value={f.inativoEm}
                        onChange={f.setInativoEm}
                        testID="cliente-completo-inativo-em"
                      />
                    </Field>
                  ) : null}

                  <Field label="Status" style={styles.colHalf}>
                    <SelectField
                      value={f.status || null}
                      onChange={(v) => f.setStatus(v == null ? "" : String(v))}
                      options={f.statusClienteOptions.map((i) => ({ value: i.codigo, label: i.descricao }))}
                      placeholder="Selecione…"
                      allowClear
                      compactWeb
                      testID="cliente-completo-status-select"
                      modalTitle="Status"
                    />
                  </Field>

                  <View style={styles.fullWidth}>
                    {f.vendedor != null ? (
                      <Text style={styles.hint} testID="cliente-completo-vendedor-hint">
                        Vendedor: #{f.vendedor}
                      </Text>
                    ) : (
                      <Text style={[styles.hint, { color: colors.warning }]}>
                        Aviso: vendedor não identificado na sessão.
                      </Text>
                    )}
                  </View>

                  <View style={styles.fullWidth}>
                    <View style={styles.historicoHeaderRow}>
                      <Text style={styles.fieldLabel}>Histórico</Text>
                      {editing ? (
                        <Pressable onPress={abrirContatosDoCliente} style={styles.verContatosBtn} testID="ver-contatos-historico">
                          <Ionicons name="time-outline" size={16} color={colors.brandPrimary} />
                          <Text style={styles.verContatosText}>Ver Contatos</Text>
                        </Pressable>
                      ) : null}
                    </View>
                    <TextInput
                      value={f.historico}
                      onChangeText={f.setHistorico}
                      placeholder="Anotações livres sobre o cliente"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, styles.textArea]}
                      multiline
                      numberOfLines={4}
                      testID="cliente-completo-historico-input"
                    />
                  </View>
                </View>
              </View>

              {/* ---- Telefones/Endereços dependem do cliente já ter sido
                   gravado (regra global: cadastros relacionados à entidade
                   principal não podem ser criados antes dela existir — ver
                   CLAUDE.md > "Global Entity Rules"). ---- */}
              {!editing ? (
                <View style={styles.card}>
                  <View style={styles.lockedRow}>
                    <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                    <Text style={styles.lockedText}>
                      Grave os Dados Principais primeiro para cadastrar telefones, endereços e contatos.
                    </Text>
                  </View>
                </View>
              ) : (
                <>
              {/* ---- Telefones (grade + formulário Incluir/Alterar/Excluir/Limpar) ---- */}
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Telefones</Text>
              </View>
              <View style={styles.card} testID="cliente-completo-telefones">
                {f.telefones.every((t) => !t.tel.trim()) ? (
                  <Text style={styles.hint}>Nenhum telefone cadastrado.</Text>
                ) : (
                  f.telefones.map((t, idx) => {
                    if (!t.tel.trim()) return null; // placeholder em branco (uso interno) — não exibir
                    const sel = f.telefoneEditIdx === idx;
                    return (
                      <Pressable
                        key={idx}
                        onPress={() => f.selecionarTelefone(idx)}
                        style={({ pressed }) => [
                          styles.gridRow,
                          sel && styles.gridRowSel,
                          pressed && { opacity: 0.8 },
                        ]}
                        testID={`cliente-completo-telefone-${idx}`}
                      >
                        <Text style={styles.gridRowText}>
                          ({t.ddd || "--"}) {t.tel}
                          {t.descricao ? ` — ${t.descricao}` : ""}
                        </Text>
                        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                      </Pressable>
                    );
                  })
                )}

                <View style={styles.gridFormDivider} />

                <View style={styles.telRow}>
                  <View style={{ width: 80 }}>
                    <Text style={styles.fieldLabel}>DDD</Text>
                    <TextInput
                      value={f.telefoneDraft.ddd}
                      onChangeText={(v) => f.updateTelefoneDraft({ ddd: v.replace(/\D/g, "").slice(0, 4) })}
                      style={styles.input}
                      keyboardType="number-pad"
                      maxLength={4}
                      placeholder="21"
                      placeholderTextColor={colors.muted}
                      testID="cliente-completo-telefone-form-ddd"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Número</Text>
                    <TextInput
                      value={f.telefoneDraft.tel}
                      onChangeText={(v) => f.updateTelefoneDraft({ tel: v.replace(/\D/g, "").slice(0, 10) })}
                      style={styles.input}
                      keyboardType="phone-pad"
                      maxLength={10}
                      placeholder="999998888"
                      placeholderTextColor={colors.muted}
                      testID="cliente-completo-telefone-form-tel"
                    />
                  </View>
                  <View style={{ flex: 1.2 }}>
                    <Text style={styles.fieldLabel}>Descrição</Text>
                    <TextInput
                      value={f.telefoneDraft.descricao}
                      onChangeText={(v) => f.updateTelefoneDraft({ descricao: v })}
                      style={styles.input}
                      placeholder="Comercial"
                      placeholderTextColor={colors.muted}
                      testID="cliente-completo-telefone-form-desc"
                    />
                  </View>
                </View>

                <View style={styles.crudBtnRow}>
                  {f.telefoneEditIdx === null ? (
                    <Pressable
                      onPress={f.incluirTelefone}
                      disabled={f.telefones.length >= 3}
                      style={({ pressed }) => [
                        styles.crudBtn,
                        styles.crudBtnPrimary,
                        (pressed || f.telefones.length >= 3) && { opacity: 0.6 },
                      ]}
                      testID="cliente-completo-telefone-incluir"
                    >
                      <Text style={styles.crudBtnPrimaryText}>Incluir</Text>
                    </Pressable>
                  ) : (
                    <>
                      <Pressable
                        onPress={f.alterarTelefone}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnPrimary, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-telefone-alterar"
                      >
                        <Text style={styles.crudBtnPrimaryText}>Alterar</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.excluirTelefone}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnDanger, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-telefone-excluir"
                      >
                        <Text style={styles.crudBtnDangerText}>Excluir</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.limparTelefoneForm}
                        style={({ pressed }) => [styles.crudBtn, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-telefone-limpar"
                      >
                        <Text style={styles.crudBtnText}>Limpar</Text>
                      </Pressable>
                    </>
                  )}
                </View>
              </View>

              {/* ---- Endereços (grade + formulário Incluir/Alterar/Excluir/Limpar) ---- */}
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Endereços</Text>
              </View>
              <View style={styles.card} testID="cliente-completo-enderecos">
                {f.enderecos.every((e) => !e.cep && !e.endereco && !e.cidade) ? (
                  <Text style={styles.hint}>Nenhum endereço cadastrado.</Text>
                ) : (
                  f.enderecos.map((e, idx) => {
                    if (!e.cep && !e.endereco && !e.cidade) return null; // placeholder em branco (uso interno)
                    const sel = f.enderecoEditIdx === idx;
                    const tipoLabel = ENDERECO_TIPOS.find((t) => t.value === e.tipo)?.label || "";
                    return (
                      <Pressable
                        key={idx}
                        onPress={() => f.selecionarEndereco(idx)}
                        style={({ pressed }) => [
                          styles.gridRow,
                          sel && styles.gridRowSel,
                          pressed && { opacity: 0.8 },
                        ]}
                        testID={`cliente-completo-endereco-${idx}`}
                      >
                        <Text style={styles.gridRowText} numberOfLines={1}>
                          [{tipoLabel}] {e.endereco}
                          {e.numero ? `, ${e.numero}` : ""}
                          {e.bairro ? ` - ${e.bairro}` : ""}
                          {e.cidade ? ` - ${e.cidade}` : ""}
                          {e.uf ? `/${e.uf}` : ""}
                        </Text>
                        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                      </Pressable>
                    );
                  })
                )}

                <View style={styles.gridFormDivider} />

                <View style={styles.radioRow}>
                  {ENDERECO_TIPOS.map((opt) => {
                    const sel = f.enderecoDraft.tipo === opt.value;
                    return (
                      <Pressable
                        key={opt.value}
                        onPress={() => f.updateEnderecoDraft({ tipo: opt.value })}
                        style={({ pressed }) => [
                          styles.radioBtn,
                          sel && styles.radioBtnSel,
                          pressed && { opacity: 0.8 },
                        ]}
                        testID={`cliente-completo-endereco-form-tipo-${opt.value}`}
                      >
                        <View style={[styles.radioCircle, sel && styles.radioCircleSel]}>
                          {sel ? <View style={styles.radioDot} /> : null}
                        </View>
                        <Text style={[styles.radioLabel, sel && { color: colors.brandPrimary }]}>{opt.label}</Text>
                      </Pressable>
                    );
                  })}
                </View>

                <View style={styles.enderecoRow}>
                  <View style={styles.enderecoCepCol}>
                    <Field label="CEP">
                      <View style={styles.inputWithBtn}>
                        <TextInput
                          value={f.enderecoDraft.cep}
                          onChangeText={f.handleCepChangeDraft}
                          style={[styles.input, { flex: 1, minWidth: 0 }]}
                          keyboardType="number-pad"
                          maxLength={8}
                          placeholder="00000000"
                          placeholderTextColor={colors.muted}
                          testID="cliente-completo-endereco-form-cep"
                        />
                        {f.cepLoadingDraft ? (
                          <ActivityIndicator color={colors.brandPrimary} style={{ marginLeft: 8 }} />
                        ) : (
                          <Pressable
                            onPress={() => f.buscarCEPDraft(f.enderecoDraft.cep)}
                            style={({ pressed }) => [styles.cepBtn, pressed && { opacity: 0.7 }]}
                            testID="cliente-completo-endereco-form-buscar-cep"
                          >
                            <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                          </Pressable>
                        )}
                      </View>
                    </Field>
                  </View>
                  <View style={styles.enderecoMainCol}>
                    <Field label="Endereço">
                      <TextInput
                        value={f.enderecoDraft.endereco}
                        onChangeText={(v) => f.updateEnderecoDraft({ endereco: v })}
                        style={styles.input}
                        placeholder="Rua/Av..."
                        placeholderTextColor={colors.muted}
                        maxLength={64}
                        testID="cliente-completo-endereco-form-logradouro"
                      />
                    </Field>
                  </View>
                  <View style={styles.enderecoNumeroCol}>
                    <Field label="Número">
                      <TextInput
                        value={f.enderecoDraft.numero}
                        onChangeText={(v) => f.updateEnderecoDraft({ numero: v.replace(/\D/g, "") })}
                        style={styles.input}
                        keyboardType="number-pad"
                        placeholder="0"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-endereco-form-numero"
                      />
                    </Field>
                  </View>
                </View>

                <View style={styles.enderecoRow}>
                  <View style={styles.enderecoCompCol}>
                    <Field label="Complemento">
                      <TextInput
                        value={f.enderecoDraft.complemento}
                        onChangeText={(v) => f.updateEnderecoDraft({ complemento: v })}
                        style={styles.input}
                        placeholder="apto, sala…"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-endereco-form-complemento"
                      />
                    </Field>
                  </View>
                  <View style={styles.enderecoBairroCol}>
                    <Field label="Bairro">
                      <TextInput
                        value={f.enderecoDraft.bairro}
                        onChangeText={(v) => f.updateEnderecoDraft({ bairro: v })}
                        style={styles.input}
                        maxLength={35}
                        placeholder="Bairro"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-endereco-form-bairro"
                      />
                    </Field>
                  </View>
                  <View style={styles.enderecoCidadeCol}>
                    <Field label="Cidade">
                      <TextInput
                        value={f.enderecoDraft.cidade}
                        onChangeText={(v) => f.updateEnderecoDraft({ cidade: v })}
                        style={styles.input}
                        maxLength={35}
                        placeholder="Cidade"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-endereco-form-cidade"
                      />
                    </Field>
                  </View>
                  <View style={styles.enderecoUfCol}>
                    <Field label="UF">
                      <TextInput
                        value={f.enderecoDraft.uf}
                        onChangeText={(v) =>
                          f.updateEnderecoDraft({ uf: v.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2) })
                        }
                        style={styles.input}
                        autoCapitalize="characters"
                        maxLength={2}
                        placeholder="RJ"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-endereco-form-uf"
                      />
                    </Field>
                  </View>
                </View>

                <View style={styles.crudBtnRow}>
                  {f.enderecoEditIdx === null ? (
                    <Pressable
                      onPress={f.incluirEndereco}
                      style={({ pressed }) => [styles.crudBtn, styles.crudBtnPrimary, pressed && { opacity: 0.7 }]}
                      testID="cliente-completo-endereco-incluir"
                    >
                      <Text style={styles.crudBtnPrimaryText}>Incluir</Text>
                    </Pressable>
                  ) : (
                    <>
                      <Pressable
                        onPress={f.alterarEndereco}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnPrimary, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-endereco-alterar"
                      >
                        <Text style={styles.crudBtnPrimaryText}>Alterar</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.excluirEndereco}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnDanger, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-endereco-excluir"
                      >
                        <Text style={styles.crudBtnDangerText}>Excluir</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.limparEnderecoForm}
                        style={({ pressed }) => [styles.crudBtn, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-endereco-limpar"
                      >
                        <Text style={styles.crudBtnText}>Limpar</Text>
                      </Pressable>
                    </>
                  )}
                </View>
              </View>
                </>
              )}
            </>
          ) : null}

          {/* ============ Dados Secundários ============ */}
          {tab === "secundarios" ? (
            <View style={styles.card} testID="cliente-completo-tab-content-secundarios">
              <View style={styles.formGrid}>
                <Field label="Tipo Cliente" style={styles.colHalf}>
                  <SelectField
                    value={f.tipo || null}
                    onChange={(v) => f.setTipo(v == null ? "" : String(v))}
                    options={f.tiposCliente.map((t) => ({ value: t.codigo, label: t.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-tipo-select"
                    modalTitle="Tipo Cliente"
                  />
                </Field>

                <Field label="Contato" style={styles.colHalf}>
                  <TextInput
                    value={f.contatoPrincipal}
                    onChangeText={f.setContatoPrincipal}
                    style={styles.input}
                    placeholder="Nome do contato principal"
                    placeholderTextColor={colors.muted}
                    maxLength={30}
                    testID="cliente-completo-contato-principal-input"
                  />
                </Field>

                <Field label="Limite de Crédito" style={styles.colHalf}>
                  <TextInput
                    value={f.limiteCredito}
                    onChangeText={f.setLimiteCredito}
                    style={styles.input}
                    keyboardType="decimal-pad"
                    placeholder="0,00"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-limite-credito-input"
                  />
                </Field>

                <Field label="Desconto (%)" style={styles.colHalf}>
                  <TextInput
                    value={f.desconto}
                    onChangeText={f.setDesconto}
                    style={styles.input}
                    keyboardType="decimal-pad"
                    placeholder="0,00"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-desconto-input"
                  />
                </Field>

                <Field label="Regime Tributário (CRT)" style={styles.colHalf}>
                  <SelectField
                    value={f.regimeTributario || null}
                    onChange={(v) => f.setRegimeTributario(v == null ? "" : String(v))}
                    options={CRT_OPTIONS}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-crt-select"
                    modalTitle="Regime Tributário"
                  />
                </Field>

                <Field label="Indicador de Presença" style={styles.colHalf}>
                  <SelectField
                    value={f.indpres || null}
                    onChange={(v) => f.setIndpres(v == null ? "" : String(v))}
                    options={INDPRES_OPTIONS}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-indpres-select"
                    modalTitle="Indicador de Presença"
                  />
                </Field>

                <Field label="Canal de Aquisição" style={styles.colHalf}>
                  <SelectField
                    value={f.canalAquisicaoCliente || null}
                    onChange={(v) => f.setCanalAquisicaoCliente(v == null ? "" : String(v))}
                    options={f.canaisAquisicao.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-canal-select"
                    modalTitle="Canal de Aquisição"
                  />
                </Field>

                <Field label="Segmento" style={styles.colHalf}>
                  <SelectField
                    value={f.segmento || null}
                    onChange={(v) => f.setSegmento(v == null ? "" : String(v))}
                    options={f.segmentos.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-segmento-select"
                    modalTitle="Segmento"
                  />
                </Field>

                <Field label="Rota" style={styles.colHalf}>
                  <SelectField
                    value={f.rota || null}
                    onChange={(v) => f.setRota(v == null ? "" : String(v))}
                    options={f.rotas.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-rota-select"
                    modalTitle="Rota"
                  />
                </Field>

                <Field label="Região" style={styles.colHalf}>
                  <SelectField
                    value={f.regiao || null}
                    onChange={(v) => f.setRegiao(v == null ? "" : String(v))}
                    options={f.regioes.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-regiao-select"
                    modalTitle="Região"
                  />
                </Field>

                <Field label="Forma de Pagamento" style={styles.colHalf}>
                  <SelectField
                    value={f.formaPagamento || null}
                    onChange={(v) => f.setFormaPagamento(v == null ? "" : String(v))}
                    options={f.formasPagamento.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-forma-pagamento-select"
                    modalTitle="Forma de Pagamento"
                  />
                </Field>

                <Field label="Dia de Contato" style={styles.colHalf}>
                  <SelectField
                    value={f.diaContato || null}
                    onChange={(v) => f.setDiaContato(v == null ? "" : String(v))}
                    options={f.diasSemana.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-dia-contato-select"
                    modalTitle="Dia de Contato"
                  />
                </Field>

                <Field label="Dia de Entrega" style={styles.colHalf}>
                  <SelectField
                    value={f.diaEntrega || null}
                    onChange={(v) => f.setDiaEntrega(v == null ? "" : String(v))}
                    options={f.diasSemana.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-dia-entrega-select"
                    modalTitle="Dia de Entrega"
                  />
                </Field>

                <Field label="E-mail Cobrança" style={styles.colHalf}>
                  <TextInput
                    value={f.emailCobranca}
                    onChangeText={f.setEmailCobranca}
                    style={styles.input}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    placeholder="cobranca@dominio.com"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-email-cobranca-input"
                  />
                </Field>

                <Field label="E-mail NFe/DANFE" style={styles.colHalf}>
                  <TextInput
                    value={f.emailNfe}
                    onChangeText={f.setEmailNfe}
                    style={styles.input}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    placeholder="nfe@dominio.com"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-email-nfe-input"
                  />
                </Field>

                <Field label="Centro de Custo" style={styles.colHalf}>
                  <SelectField
                    value={f.centroCustoCliente || null}
                    onChange={(v) => f.setCentroCustoCliente(v == null ? "" : String(v))}
                    options={f.centrosCusto.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-centro-custo-select"
                    modalTitle="Centro de Custo"
                  />
                </Field>

                <Field label="Conta p/ Transf. Caixa" style={styles.colHalf}>
                  <SelectField
                    value={f.contaTransfCaixa || null}
                    onChange={(v) => f.setContaTransfCaixa(v == null ? "" : String(v))}
                    options={f.contasLista.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-conta-transf-select"
                    modalTitle="Conta p/ Transferência"
                  />
                </Field>

                <Field label="Classe Caixa" style={styles.colHalf}>
                  <SelectField
                    value={f.classeCaixa || null}
                    onChange={(v) => f.setClasseCaixa(v == null ? "" : String(v))}
                    options={f.classes.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-classe-caixa-select"
                    modalTitle="Classe Caixa"
                  />
                </Field>

                <Field label="Sub-Classe Caixa" style={styles.colHalf}>
                  <SelectField
                    value={f.subClasseCaixa || null}
                    onChange={(v) => f.setSubClasseCaixa(v == null ? "" : String(v))}
                    options={f.subClasses.map((i) => ({ value: i.codigo, label: i.descricao }))}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cliente-completo-sub-classe-caixa-select"
                    modalTitle="Sub-Classe Caixa"
                  />
                </Field>

                <Field label="Valor do Frete" style={styles.colHalf}>
                  <TextInput
                    value={f.valorFrete}
                    onChangeText={f.setValorFrete}
                    style={styles.input}
                    keyboardType="decimal-pad"
                    placeholder="0,00"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-valor-frete-input"
                  />
                </Field>

                <Field label="Prazo de Faturamento (dias)" style={styles.colHalf}>
                  <TextInput
                    value={f.prazoFaturamento}
                    onChangeText={(v) => f.setPrazoFaturamento(v.replace(/\D/g, ""))}
                    style={styles.input}
                    keyboardType="number-pad"
                    placeholder="0"
                    placeholderTextColor={colors.muted}
                    testID="cliente-completo-prazo-faturamento-input"
                  />
                </Field>

                <View style={styles.fullWidth}>
                  <View style={styles.switchRow}>
                    <Text style={styles.switchLabel}>Não Contribuinte (ICMS)</Text>
                    <Switch
                      value={f.creditaIcms}
                      onValueChange={f.setCreditaIcms}
                      trackColor={{ false: colors.border, true: colors.brandSecondary }}
                      thumbColor={f.creditaIcms ? colors.brandPrimary : "#f4f3f4"}
                      testID="cliente-completo-credita-icms-switch"
                    />
                  </View>
                  <View style={styles.switchRow}>
                    <Text style={styles.switchLabel}>Consumidor Final</Text>
                    <Switch
                      value={f.consumidorFinal}
                      onValueChange={f.setConsumidorFinal}
                      trackColor={{ false: colors.border, true: colors.brandSecondary }}
                      thumbColor={f.consumidorFinal ? colors.brandPrimary : "#f4f3f4"}
                      testID="cliente-completo-consumidor-final-switch"
                    />
                  </View>
                  <View style={styles.switchRow}>
                    <Text style={styles.switchLabel}>Tributa ISS Fora do Município</Text>
                    <Switch
                      value={f.tributaIssForaMunicipio}
                      onValueChange={f.setTributaIssForaMunicipio}
                      trackColor={{ false: colors.border, true: colors.brandSecondary }}
                      thumbColor={f.tributaIssForaMunicipio ? colors.brandPrimary : "#f4f3f4"}
                      testID="cliente-completo-tributa-iss-switch"
                    />
                  </View>
                </View>

                <View style={styles.fullWidth}>
                  <View style={styles.switchRow}>
                    <Text style={styles.switchLabel}>Fatura Para (cliente principal centraliza a fatura)</Text>
                    <Switch
                      value={f.faturaPara}
                      onValueChange={f.setFaturaPara}
                      trackColor={{ false: colors.border, true: colors.brandSecondary }}
                      thumbColor={f.faturaPara ? colors.brandPrimary : "#f4f3f4"}
                      testID="cliente-completo-fatura-para-switch"
                    />
                  </View>
                  {f.faturaPara ? (
                    <View style={styles.enderecoRow}>
                      <View style={{ width: 140 }}>
                        <Field label="Cód. Cliente Principal">
                          <TextInput
                            value={f.clientePrincipal}
                            onChangeText={(v) => f.setClientePrincipal(v.replace(/\D/g, ""))}
                            onBlur={() => f.buscarClientePrincipal(f.clientePrincipal)}
                            style={styles.input}
                            keyboardType="number-pad"
                            placeholder="Código"
                            placeholderTextColor={colors.muted}
                            testID="cliente-completo-cliente-principal-input"
                          />
                        </Field>
                      </View>
                      {f.clientePrincipalNome ? (
                        <Text style={[styles.hint, { alignSelf: "center" }]}>{f.clientePrincipalNome}</Text>
                      ) : null}
                    </View>
                  ) : null}
                </View>

                <View style={styles.fullWidth}>
                  <View style={styles.switchRow}>
                    <Text style={styles.switchLabel}>Cobra Tarifa Bancária</Text>
                    <Switch
                      value={f.cobraTarifaBancaria}
                      onValueChange={f.setCobraTarifaBancaria}
                      trackColor={{ false: colors.border, true: colors.brandSecondary }}
                      thumbColor={f.cobraTarifaBancaria ? colors.brandPrimary : "#f4f3f4"}
                      testID="cliente-completo-cobra-tarifa-switch"
                    />
                  </View>
                  {f.cobraTarifaBancaria ? (
                    <View style={styles.radioRow}>
                      {([
                        { value: "B" as const, label: "Boleto" },
                        { value: "N" as const, label: "NFe" },
                      ]).map((opt) => {
                        const sel = f.tipoCobrancaTarifa === opt.value;
                        return (
                          <Pressable
                            key={opt.value}
                            onPress={() => f.setTipoCobrancaTarifa(opt.value)}
                            style={({ pressed }) => [
                              styles.radioBtn,
                              sel && styles.radioBtnSel,
                              pressed && { opacity: 0.8 },
                            ]}
                            testID={`cliente-completo-tipo-cobranca-${opt.value}`}
                          >
                            <View style={[styles.radioCircle, sel && styles.radioCircleSel]}>
                              {sel ? <View style={styles.radioDot} /> : null}
                            </View>
                            <Text style={[styles.radioLabel, sel && { color: colors.brandPrimary }]}>{opt.label}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  ) : null}
                </View>
              </View>

              <View style={styles.emBreveBox}>
                <Ionicons name="construct-outline" size={20} color={colors.muted} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.emBreveTitle}>Em breve</Text>
                  <Text style={styles.emBreveHint}>
                    Os itens abaixo dependem de infraestrutura própria (upload de arquivo, tabela
                    ano-a-ano) e ficam para uma próxima iteração:
                  </Text>
                  {SECUNDARIOS_EM_BREVE.map((item) => (
                    <Text key={item} style={styles.emBreveItem}>
                      • {item}
                    </Text>
                  ))}
                </View>
              </View>
            </View>
          ) : null}

          {/* ============ Contatos (grade + formulário Incluir/Alterar/Excluir/Limpar) ============ */}
          {tab === "contatos" ? (
            <>
              <View style={styles.sectionHeader} testID="cliente-completo-tab-content-contatos">
                <Text style={styles.sectionTitle}>Pessoas de Contato</Text>
              </View>

              <View style={styles.card} testID="cliente-completo-contatos">
                {f.contatos.every((ct) => !ct.contato.trim()) ? (
                  <Text style={styles.hint}>Nenhum contato cadastrado.</Text>
                ) : (
                  f.contatos.map((ct, idx) => {
                    if (!ct.contato.trim()) return null; // placeholder em branco (uso interno)
                    const sel = f.contatoEditIdx === idx;
                    const detalhes = [ct.setor, ct.cargo].filter(Boolean).join(" / ");
                    const tel = ct.telefone || ct.celular;
                    return (
                      <Pressable
                        key={idx}
                        onPress={() => f.selecionarContato(idx)}
                        style={({ pressed }) => [
                          styles.gridRow,
                          sel && styles.gridRowSel,
                          pressed && { opacity: 0.8 },
                        ]}
                        testID={`cliente-completo-contato-${idx}`}
                      >
                        <Text style={styles.gridRowText} numberOfLines={1}>
                          {ct.contato}
                          {detalhes ? ` — ${detalhes}` : ""}
                          {tel ? ` — ${tel}` : ""}
                        </Text>
                        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                      </Pressable>
                    );
                  })
                )}

                <View style={styles.gridFormDivider} />

                <View style={styles.enderecoRow}>
                  <View style={{ flex: 1.6 }}>
                    <Field label="Contato *">
                      <TextInput
                        value={f.contatoDraft.contato}
                        onChangeText={(v) => f.updateContatoDraft({ contato: v })}
                        style={styles.input}
                        placeholder="Nome do contato"
                        placeholderTextColor={colors.muted}
                        maxLength={30}
                        testID="cliente-completo-contato-form-nome"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Field label="Setor">
                      <TextInput
                        value={f.contatoDraft.setor}
                        onChangeText={(v) => f.updateContatoDraft({ setor: v })}
                        style={styles.input}
                        placeholder="Setor"
                        placeholderTextColor={colors.muted}
                        maxLength={30}
                        testID="cliente-completo-contato-form-setor"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Field label="Cargo">
                      <TextInput
                        value={f.contatoDraft.cargo}
                        onChangeText={(v) => f.updateContatoDraft({ cargo: v })}
                        style={styles.input}
                        placeholder="Cargo"
                        placeholderTextColor={colors.muted}
                        maxLength={30}
                        testID="cliente-completo-contato-form-cargo"
                      />
                    </Field>
                  </View>
                </View>

                <View style={styles.enderecoRow}>
                  <View style={{ width: 60 }}>
                    <Field label="DDD">
                      <TextInput
                        value={f.contatoDraft.ddd}
                        onChangeText={(v) => f.updateContatoDraft({ ddd: v.replace(/\D/g, "").slice(0, 3) })}
                        style={styles.input}
                        keyboardType="number-pad"
                        maxLength={3}
                        testID="cliente-completo-contato-form-ddd"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Field label="Telefone">
                      <TextInput
                        value={f.contatoDraft.telefone}
                        onChangeText={(v) => f.updateContatoDraft({ telefone: v })}
                        style={styles.input}
                        keyboardType="phone-pad"
                        placeholder="Telefone"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-contato-form-telefone"
                      />
                    </Field>
                  </View>
                  <View style={{ width: 60 }}>
                    <Field label="DDD Fax">
                      <TextInput
                        value={f.contatoDraft.ddd_fax}
                        onChangeText={(v) => f.updateContatoDraft({ ddd_fax: v.replace(/\D/g, "").slice(0, 3) })}
                        style={styles.input}
                        keyboardType="number-pad"
                        maxLength={3}
                        testID="cliente-completo-contato-form-ddd-fax"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Field label="Fax">
                      <TextInput
                        value={f.contatoDraft.fax}
                        onChangeText={(v) => f.updateContatoDraft({ fax: v })}
                        style={styles.input}
                        keyboardType="phone-pad"
                        placeholder="Fax"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-contato-form-fax"
                      />
                    </Field>
                  </View>
                </View>

                <View style={styles.enderecoRow}>
                  <View style={{ width: 60 }}>
                    <Field label="DDD Cel.">
                      <TextInput
                        value={f.contatoDraft.ddd_celular}
                        onChangeText={(v) =>
                          f.updateContatoDraft({ ddd_celular: v.replace(/\D/g, "").slice(0, 3) })
                        }
                        style={styles.input}
                        keyboardType="number-pad"
                        maxLength={3}
                        testID="cliente-completo-contato-form-ddd-celular"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Field label="Celular">
                      <TextInput
                        value={f.contatoDraft.celular}
                        onChangeText={(v) => f.updateContatoDraft({ celular: v })}
                        style={styles.input}
                        keyboardType="phone-pad"
                        placeholder="Celular"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-contato-form-celular"
                      />
                    </Field>
                  </View>
                  <View style={{ flex: 1.4 }}>
                    <Field label="E-mail">
                      <TextInput
                        value={f.contatoDraft.e_mail}
                        onChangeText={(v) => f.updateContatoDraft({ e_mail: v })}
                        style={styles.input}
                        keyboardType="email-address"
                        autoCapitalize="none"
                        placeholder="email@dominio.com"
                        placeholderTextColor={colors.muted}
                        testID="cliente-completo-contato-form-email"
                      />
                    </Field>
                  </View>
                  <View style={{ width: 130 }}>
                    <Field label="Sexo">
                      <SelectField
                        value={f.contatoDraft.sexo || null}
                        onChange={(v) => f.updateContatoDraft({ sexo: v == null ? "" : String(v) })}
                        options={[
                          { value: "M", label: "Masculino" },
                          { value: "F", label: "Feminino" },
                        ]}
                        placeholder="—"
                        allowClear
                        compactWeb
                        testID="cliente-completo-contato-form-sexo"
                        modalTitle="Sexo"
                      />
                    </Field>
                  </View>
                </View>

                <View style={styles.crudBtnRow}>
                  {f.contatoEditIdx === null ? (
                    <Pressable
                      onPress={f.incluirContato}
                      style={({ pressed }) => [styles.crudBtn, styles.crudBtnPrimary, pressed && { opacity: 0.7 }]}
                      testID="cliente-completo-contato-incluir"
                    >
                      <Text style={styles.crudBtnPrimaryText}>Incluir</Text>
                    </Pressable>
                  ) : (
                    <>
                      <Pressable
                        onPress={f.alterarContato}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnPrimary, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-contato-alterar"
                      >
                        <Text style={styles.crudBtnPrimaryText}>Alterar</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.excluirContato}
                        style={({ pressed }) => [styles.crudBtn, styles.crudBtnDanger, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-contato-excluir"
                      >
                        <Text style={styles.crudBtnDangerText}>Excluir</Text>
                      </Pressable>
                      <Pressable
                        onPress={f.limparContatoForm}
                        style={({ pressed }) => [styles.crudBtn, pressed && { opacity: 0.7 }]}
                        testID="cliente-completo-contato-limpar"
                      >
                        <Text style={styles.crudBtnText}>Limpar</Text>
                      </Pressable>
                    </>
                  )}
                </View>
              </View>
            </>
          ) : null}

          {/* ============ Anexos (Gestor de Documentos) ============ */}
          {tab === "anexos" && codigo != null ? (
            <>
              <View style={styles.sectionHeader} testID="cliente-completo-tab-content-anexos">
                <Text style={styles.sectionTitle}>Documentos Anexados</Text>
              </View>
              <View style={styles.card}>
                <GestorDocumentosSection
                  api={f.conn?.api || ""}
                  servidor={f.conn?.servidor || ""}
                  banco={f.conn?.banco || ""}
                  codGrupo={GESTOR_DOC_GRUPO_CLIENTE}
                  codigoEntidade={codigo}
                />
              </View>
            </>
          ) : null}
        </View>
      </ScrollView>

      {f.toastMsg ? (
        <View
          style={[styles.toast, TOAST_SHADOW_STYLE, { backgroundColor: toastBackgroundColor(f.toastTone) }]}
          testID="cliente-completo-toast"
        >
          <Text style={styles.toastText}>{f.toastMsg}</Text>
        </View>
      ) : null}

      <AppModal visible={contatosHistOpen} transparent animationType="slide" onRequestClose={() => setContatosHistOpen(false)}>
        <Pressable style={styles.modalBgWeb} onPress={() => setContatosHistOpen(false)}>
          <Pressable style={styles.modalCardWeb} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeaderRow}>
              <Text style={styles.modalTitleText}>Contatos de {f.nome || "cliente"}</Text>
              <Pressable onPress={() => setContatosHistOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {contatosHistLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : (
              <ScrollView style={{ maxHeight: 420 }}>
                {contatosHist.length === 0 ? (
                  <Text style={styles.hint}>Nenhum contato registrado para este cliente.</Text>
                ) : contatosHist.map((c) => (
                  <View key={c.codigo} style={styles.contatoHistRow} testID={`contato-hist-${c.codigo}`}>
                    <View style={styles.contatoHistTop}>
                      <Text style={styles.contatoHistData}>{isoToBR(c.data)}</Text>
                      {c.tipo_cliente_nome ? <Text style={styles.contatoHistTipo}>{c.tipo_cliente_nome}</Text> : null}
                    </View>
                    <Text style={styles.contatoHistSub}>
                      {c.contato || "sem contato"}{c.profissional_nome ? ` · ${c.profissional_nome}` : ""}
                      {c.data_prev ? ` · Previsão: ${isoToBR(c.data_prev)}` : ""}
                    </Text>
                    {c.obs ? <Text style={styles.contatoHistObs} numberOfLines={2}>{c.obs}</Text> : null}
                  </View>
                ))}
              </ScrollView>
            )}
            <Pressable
              onPress={() => { setContatosHistOpen(false); router.push("/contatos" as never); }}
              style={styles.fullListBtnCliente}
              testID="ver-todos-contatos"
            >
              <Text style={styles.fullListBtnClienteText}>Abrir tela de Contatos</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

// ---------- Componente auxiliar Field ----------
function Field({
  label,
  children,
  style,
}: {
  label: string;
  children: React.ReactNode;
  style?: object;
}) {
  return (
    <View style={[{ marginBottom: spacing.md }, style]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.3)",
    minWidth: 90,
    justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  tabBar: {
    flexDirection: "row",
    gap: spacing.sm,
    marginBottom: spacing.lg,
    flexWrap: "wrap",
  },
  tabBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  formGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.md },
  colHalf: { width: "49%" },
  fullWidth: { width: "100%" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.onSurface,
    minHeight: 40,
  },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  inputError: { borderColor: colors.error },
  errorText: { fontSize: 12, color: colors.error, marginTop: 4 },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-start",
    gap: 12,
    paddingVertical: 6,
    marginTop: 4,
  },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  emailRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  emailSwitchInline: { alignItems: "center", gap: 2 },
  emailSwitchLabel: { fontSize: 10, color: colors.muted, textAlign: "center" },
  hint: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, fontStyle: "italic" },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
    width: "100%",
    maxWidth: 1120,
    alignSelf: "center",
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "500",
    color: colors.onSurface,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  telRow: { flexDirection: "row", alignItems: "flex-end", gap: 8, marginBottom: spacing.md },
  gridRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 10,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "transparent",
    marginBottom: 6,
  },
  gridRowSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  gridFormDivider: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  crudBtnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  crudBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  crudBtnText: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  crudBtnDanger: { backgroundColor: colors.surface, borderColor: colors.error },
  crudBtnDangerText: { fontSize: 13, fontWeight: "600", color: colors.error },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: spacing.md },
  radioBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  inputWithBtn: { flexDirection: "row", alignItems: "center", minWidth: 0 },
  enderecoRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  enderecoCepCol: { width: 200, minWidth: 0 },
  enderecoMainCol: { flex: 1.6 },
  enderecoNumeroCol: { width: 110 },
  enderecoCompCol: { flex: 1.2 },
  enderecoBairroCol: { flex: 1.1 },
  enderecoCidadeCol: { flex: 1 },
  enderecoUfCol: { width: 86 },
  cepBtn: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.sm,
    backgroundColor: colors.brandPrimary,
    marginLeft: 8,
  },
  emBreveBox: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  emBreveTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface, marginBottom: 4 },
  emBreveHint: { fontSize: 12, color: colors.muted, lineHeight: 17, marginBottom: 6 },
  emBreveItem: { fontSize: 12, color: colors.muted, lineHeight: 18 },
  toast: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    top: "45%",
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
  historicoHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 },
  verContatosBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  verContatosText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  modalBgWeb: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", paddingHorizontal: spacing.xl,
  },
  modalCardWeb: {
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    width: "100%", maxWidth: 560, alignSelf: "center", padding: spacing.lg, maxHeight: "85%",
  },
  modalHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitleText: { fontSize: 16, fontWeight: "700", color: colors.onSurface, flex: 1 },
  contatoHistRow: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  contatoHistTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  contatoHistData: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  contatoHistTipo: { fontSize: 11, color: colors.brandPrimary, fontWeight: "700" },
  contatoHistSub: { fontSize: 13, color: colors.onSurface, marginTop: 4 },
  contatoHistObs: { fontSize: 12, color: colors.muted, marginTop: 4 },
  fullListBtnCliente: {
    borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 12, alignItems: "center", marginTop: spacing.md,
  },
  fullListBtnClienteText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 14 },
});
