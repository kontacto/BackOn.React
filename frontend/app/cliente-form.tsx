import { useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Modal,
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

import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";
import { useClienteForm, ENDERECO_TIPOS, toastBackgroundColor } from "@/src/hooks/useClienteForm";

const TOAST_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 6px 12px rgba(0, 0, 0, 0.35)" }
    : {
        shadowColor: "#000",
        shadowOpacity: 0.35,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 6 },
        elevation: 12,
      };

// ============================================================
// Tela — Cadastro rápido de cliente (mobile + web)
// Usado em fluxos de pré-venda (Pedidos/O.S.) e cadastro simples.
// Para o cadastro completo (web-only), ver app/cliente-completo.tsx.
// ============================================================
export default function ClienteFormScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const isWeb = Platform.OS === "web";
  const params = useLocalSearchParams<{ codigo?: string; initial_nome?: string }>();
  const editing = !!params.codigo;
  const codigo = params.codigo ? parseInt(String(params.codigo), 10) : null;

  const [tipoModalVisible, setTipoModalVisible] = useState(false);

  const f = useClienteForm({
    editing,
    codigo,
    initialNome: params.initial_nome ? String(params.initial_nome) : undefined,
    selfRoute: "/cliente-form",
  });

  // Cadastro rápido edita apenas o primeiro endereço (cadastro completo, web-only,
  // expõe a lista inteira com incluir/excluir).
  const endereco = f.enderecos[0];
  const setEndereco = (updater: (prev: typeof endereco) => typeof endereco) =>
    f.updateEndereco(0, updater(endereco));

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
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cliente-form-screen">
      {/* Header sticky */}
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="cliente-form-back-button"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Cliente #${codigo}` : "Novo Cliente"}
        </Text>
        {can("CLIENTE.GRAVAR") ? (
          <Pressable
            onPress={() => f.handleSave(() => router.back())}
            disabled={f.saving}
            style={({ pressed }) => [
              styles.saveBtn,
              (pressed || f.saving) && { opacity: 0.7 },
            ]}
            hitSlop={8}
            testID="cliente-form-save-button"
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

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 0}
      >
        <ScrollView
          contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ============ Dados Principais ============ */}
          <Text style={styles.sectionTitle}>Dados Principais</Text>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <View style={isWeb ? styles.formGridWeb : undefined}>
              <Field label={`CGC/CPF ${f.docType === "UNKNOWN" ? "" : `(${f.docType})`}`} style={isWeb ? styles.colHalf : undefined}>
              <TextInput
                value={f.cgcCpf}
                onChangeText={f.handleCgcCpfChange}
                onBlur={f.buscarPorCgc}
                placeholder="CPF (11) ou CNPJ (14, aceita letras)"
                placeholderTextColor={colors.muted}
                style={styles.input}
                autoCapitalize="characters"
                testID="cliente-form-cgc-cpf-input"
              />
              </Field>

              <Field label="Nome / Razão Social *" style={isWeb ? styles.colHalf : undefined}>
              <TextInput
                value={f.nome}
                onChangeText={f.setNome}
                placeholder="Nome do cliente"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={60}
                testID="cliente-form-nome-input"
              />
              </Field>

              <Field label="E-mail" style={isWeb ? styles.colHalf : undefined}>
              <TextInput
                value={f.email}
                onChangeText={f.setEmail}
                placeholder="email@dominio.com"
                placeholderTextColor={colors.muted}
                style={styles.input}
                keyboardType="email-address"
                autoCapitalize="none"
                testID="cliente-form-email-input"
              />
              </Field>

              <Field label={f.labelInscre} style={isWeb ? styles.colHalf : undefined}>
              <TextInput
                value={f.inscre}
                onChangeText={f.setInscre}
                placeholder={f.labelInscre}
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={18}
                testID="cliente-form-inscre-input"
              />
              </Field>

              <Field label="Tipo Cliente" style={isWeb ? styles.colHalf : undefined}>
              <Pressable
                onPress={() => setTipoModalVisible(true)}
                style={({ pressed }) => [styles.input, styles.dropdown, pressed && { opacity: 0.7 }]}
                testID="cliente-form-tipo-dropdown"
              >
                <Text
                  style={[
                    styles.dropdownText,
                    !f.tipoSelecionadoLabel && { color: colors.muted },
                  ]}
                  numberOfLines={1}
                >
                  {f.tipoSelecionadoLabel || "Selecione…"}
                </Text>
                <Ionicons name="chevron-down" size={16} color={colors.muted} />
              </Pressable>
              </Field>

              <View style={isWeb ? styles.fullWidth : undefined}>
                <View style={[styles.switchRow, isWeb && styles.switchRowWeb]}>
                  <Text style={styles.switchLabel}>Aceita receber e-mail</Text>
                  <Switch
                    value={f.aceitaEmail}
                    onValueChange={f.setAceitaEmail}
                    trackColor={{ false: colors.border, true: colors.brandSecondary }}
                    thumbColor={f.aceitaEmail ? colors.brandPrimary : "#f4f3f4"}
                    testID="cliente-form-aceita-email-switch"
                  />
                </View>

                {f.vendedor != null ? (
                  <Text style={styles.hint} testID="cliente-form-vendedor-hint">
                    Vendedor: #{f.vendedor}
                  </Text>
                ) : (
                  <Text style={[styles.hint, { color: colors.warning }]}>
                    Aviso: vendedor não identificado na sessão.
                  </Text>
                )}
              </View>
            </View>
          </View>

          {/* ============ Telefones ============ */}
          <View style={[styles.sectionHeader, isWeb && styles.sectionHeaderCompactWeb]}>
            <Text style={styles.sectionTitle}>Telefones</Text>
            <Pressable
              onPress={f.addTelefone}
              disabled={f.telefones.length >= 3}
              style={({ pressed }) => [
                styles.addBtn,
                (pressed || f.telefones.length >= 3) && { opacity: 0.5 },
              ]}
              testID="cliente-form-add-telefone-button"
            >
              <Ionicons name="add" size={16} color={colors.brandPrimary} />
              <Text style={styles.addBtnText}>Adicionar</Text>
            </Pressable>
          </View>
          <View style={[styles.card, isWeb && styles.cardCompactWeb]}>
            {f.telefones.map((t, idx) => (
              <View key={idx} style={styles.telRow} testID={`cliente-form-telefone-${idx}`}>
                <View style={{ width: 64 }}>
                  <Text style={styles.fieldLabel}>DDD</Text>
                  <TextInput
                    value={t.ddd}
                    onChangeText={(v) =>
                      f.updateTelefone(idx, { ddd: v.replace(/\D/g, "").slice(0, 4) })
                    }
                    style={styles.input}
                    keyboardType="number-pad"
                    maxLength={4}
                    placeholder="21"
                    placeholderTextColor={colors.muted}
                    testID={`cliente-form-telefone-${idx}-ddd`}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Número</Text>
                  <TextInput
                    value={t.tel}
                    onChangeText={(v) =>
                      f.updateTelefone(idx, { tel: v.replace(/\D/g, "").slice(0, 10) })
                    }
                    style={styles.input}
                    keyboardType="phone-pad"
                    maxLength={10}
                    placeholder="999998888"
                    placeholderTextColor={colors.muted}
                    testID={`cliente-form-telefone-${idx}-tel`}
                  />
                </View>
                <View style={{ flex: 1.2 }}>
                  <Text style={styles.fieldLabel}>Descrição</Text>
                  <TextInput
                    value={t.descricao}
                    onChangeText={(v) => f.updateTelefone(idx, { descricao: v })}
                    style={styles.input}
                    placeholder="Comercial"
                    placeholderTextColor={colors.muted}
                    testID={`cliente-form-telefone-${idx}-desc`}
                  />
                </View>
                {f.telefones.length > 1 ? (
                  <Pressable
                    onPress={() => f.removeTelefone(idx)}
                    style={({ pressed }) => [styles.delBtn, pressed && { opacity: 0.7 }]}
                    testID={`cliente-form-telefone-${idx}-remove`}
                    hitSlop={8}
                  >
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>

          {/* ============ Endereço ============ */}
          <Text style={[styles.sectionTitle, isWeb && styles.sectionTitleCompactWeb]}>Endereço</Text>
          <View style={[styles.card, isWeb && styles.cardCompactWeb]}>
            <Text style={styles.fieldLabel}>Tipo</Text>
            <View style={styles.radioRow}>
              {ENDERECO_TIPOS.map((opt) => {
                const sel = endereco.tipo === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    onPress={() => setEndereco((p) => ({ ...p, tipo: opt.value }))}
                    style={({ pressed }) => [
                      styles.radioBtn,
                      sel && styles.radioBtnSel,
                      pressed && { opacity: 0.8 },
                    ]}
                    testID={`cliente-form-endereco-tipo-${opt.value}`}
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

            {isWeb ? (
              <View style={styles.enderecoRowWeb}>
                <View style={styles.enderecoCepColWeb}>
                  <Field label="CEP">
                    <View style={styles.inputWithBtn}>
                      <TextInput
                        value={endereco.cep}
                        onChangeText={(txt) => f.handleCepChange(0, txt)}
                        style={[styles.input, { flex: 1, minWidth: 0 }]}
                        keyboardType="number-pad"
                        maxLength={8}
                        placeholder="00000000"
                        placeholderTextColor={colors.muted}
                        testID="cliente-form-endereco-cep"
                      />
                      {(f.cepLoadingIdx === 0) ? (
                        <ActivityIndicator
                          color={colors.brandPrimary}
                          style={{ marginLeft: 8 }}
                        />
                      ) : (
                        <Pressable
                          onPress={() => f.buscarCEP(0, endereco.cep)}
                          style={({ pressed }) => [
                            styles.cepBtn,
                            pressed && { opacity: 0.7 },
                          ]}
                          testID="cliente-form-endereco-buscar-cep"
                        >
                          <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                        </Pressable>
                      )}
                    </View>
                  </Field>
                </View>
                <View style={styles.enderecoMainColWeb}>
                  <Field label="Endereço">
                    <TextInput
                      value={endereco.endereco}
                      onChangeText={(v) => setEndereco((p) => ({ ...p, endereco: v }))}
                      style={styles.input}
                      placeholder="Rua/Av..."
                      placeholderTextColor={colors.muted}
                      maxLength={64}
                      testID="cliente-form-endereco-logradouro"
                    />
                  </Field>
                </View>
              </View>
            ) : (
              <>
                <Field label="CEP">
                  <View style={styles.inputWithBtn}>
                    <TextInput
                      value={endereco.cep}
                      onChangeText={(txt) => f.handleCepChange(0, txt)}
                      style={[styles.input, { flex: 1, minWidth: 0 }]}
                      keyboardType="number-pad"
                      maxLength={8}
                      placeholder="00000000"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-cep"
                    />
                    {(f.cepLoadingIdx === 0) ? (
                      <ActivityIndicator
                        color={colors.brandPrimary}
                        style={{ marginLeft: 8 }}
                      />
                    ) : (
                      <Pressable
                        onPress={() => f.buscarCEP(0, endereco.cep)}
                        style={({ pressed }) => [
                          styles.cepBtn,
                          pressed && { opacity: 0.7 },
                        ]}
                        testID="cliente-form-endereco-buscar-cep"
                      >
                        <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                      </Pressable>
                    )}
                  </View>
                </Field>

                <Field label="Endereço">
                  <TextInput
                    value={endereco.endereco}
                    onChangeText={(v) => setEndereco((p) => ({ ...p, endereco: v }))}
                    style={styles.input}
                    placeholder="Rua/Av..."
                    placeholderTextColor={colors.muted}
                    maxLength={64}
                    testID="cliente-form-endereco-logradouro"
                  />
                </Field>
              </>
            )}

            {isWeb ? (
              <View style={styles.row2}>
                <View style={{ width: 110 }}>
                  <Field label="Número">
                    <TextInput
                      value={endereco.numero}
                      onChangeText={(v) =>
                        setEndereco((p) => ({ ...p, numero: v.replace(/\D/g, "") }))
                      }
                      style={styles.input}
                      keyboardType="number-pad"
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-numero"
                    />
                  </Field>
                </View>
              </View>
            ) : (
              <View style={styles.row2}>
                <View style={{ width: 110 }}>
                  <Field label="Número">
                    <TextInput
                      value={endereco.numero}
                      onChangeText={(v) =>
                        setEndereco((p) => ({ ...p, numero: v.replace(/\D/g, "") }))
                      }
                      style={styles.input}
                      keyboardType="number-pad"
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-numero"
                    />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Complemento">
                    <TextInput
                      value={endereco.complemento}
                      onChangeText={(v) => setEndereco((p) => ({ ...p, complemento: v }))}
                      style={styles.input}
                      placeholder="apto, sala…"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-complemento"
                    />
                  </Field>
                </View>
              </View>
            )}

            {isWeb ? (
              <View style={styles.enderecoRowWeb}>
                <View style={styles.enderecoCompColWeb}>
                  <Field label="Complemento">
                    <TextInput
                      value={endereco.complemento}
                      onChangeText={(v) => setEndereco((p) => ({ ...p, complemento: v }))}
                      style={styles.input}
                      placeholder="apto, sala…"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-complemento"
                    />
                  </Field>
                </View>
                <View style={styles.enderecoBairroColWeb}>
                  <Field label="Bairro">
                    <TextInput
                      value={endereco.bairro}
                      onChangeText={(v) => setEndereco((p) => ({ ...p, bairro: v }))}
                      style={styles.input}
                      maxLength={35}
                      placeholder="Bairro"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-bairro"
                    />
                  </Field>
                </View>
                <View style={styles.enderecoCidadeColWeb}>
                  <Field label="Cidade">
                    <TextInput
                      value={endereco.cidade}
                      onChangeText={(v) => setEndereco((p) => ({ ...p, cidade: v }))}
                      style={styles.input}
                      maxLength={35}
                      placeholder="Cidade"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-cidade"
                    />
                  </Field>
                </View>
                <View style={styles.enderecoUfColWeb}>
                  <Field label="UF">
                    <TextInput
                      value={endereco.uf}
                      onChangeText={(v) =>
                        setEndereco((p) => ({
                          ...p,
                          uf: v.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2),
                        }))
                      }
                      style={styles.input}
                      autoCapitalize="characters"
                      maxLength={2}
                      placeholder="RJ"
                      placeholderTextColor={colors.muted}
                      testID="cliente-form-endereco-uf"
                    />
                  </Field>
                </View>
              </View>
            ) : (
              <>
                <Field label="Bairro">
                  <TextInput
                    value={endereco.bairro}
                    onChangeText={(v) => setEndereco((p) => ({ ...p, bairro: v }))}
                    style={styles.input}
                    maxLength={35}
                    placeholder="Bairro"
                    placeholderTextColor={colors.muted}
                    testID="cliente-form-endereco-bairro"
                  />
                </Field>

                <View style={styles.row2}>
                  <View style={{ flex: 1 }}>
                    <Field label="Cidade">
                      <TextInput
                        value={endereco.cidade}
                        onChangeText={(v) => setEndereco((p) => ({ ...p, cidade: v }))}
                        style={styles.input}
                        maxLength={35}
                        placeholder="Cidade"
                        placeholderTextColor={colors.muted}
                        testID="cliente-form-endereco-cidade"
                      />
                    </Field>
                  </View>
                  <View style={{ width: 90 }}>
                    <Field label="UF">
                      <TextInput
                        value={endereco.uf}
                        onChangeText={(v) =>
                          setEndereco((p) => ({
                            ...p,
                            uf: v.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2),
                          }))
                        }
                        style={styles.input}
                        autoCapitalize="characters"
                        maxLength={2}
                        placeholder="RJ"
                        placeholderTextColor={colors.muted}
                        testID="cliente-form-endereco-uf"
                      />
                    </Field>
                  </View>
                </View>
              </>
            )}
          </View>

          <View style={{ height: spacing.xxl }} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* ========= Modal Tipo Cliente ========= */}
      <Modal
        visible={tipoModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setTipoModalVisible(false)}
      >
        <Pressable
          style={styles.modalBackdrop}
          onPress={() => setTipoModalVisible(false)}
          testID="cliente-form-tipo-modal-backdrop"
        >
          <Pressable
            style={styles.modalCard}
            onPress={(e) => e.stopPropagation()}
          >
            <Text style={styles.modalTitle}>Tipo Cliente</Text>
            <ScrollView style={{ maxHeight: 360 }}>
              <Pressable
                onPress={() => {
                  f.setTipo("");
                  setTipoModalVisible(false);
                }}
                style={({ pressed }) => [styles.modalOpt, pressed && { opacity: 0.7 }]}
              >
                <Text style={[styles.modalOptText, { color: colors.muted }]}>
                  (Nenhum)
                </Text>
              </Pressable>
              {f.tiposCliente.map((t) => {
                const sel = String(t.codigo) === f.tipo;
                return (
                  <Pressable
                    key={t.codigo}
                    onPress={() => {
                      f.setTipo(String(t.codigo));
                      setTipoModalVisible(false);
                    }}
                    style={({ pressed }) => [
                      styles.modalOpt,
                      sel && { backgroundColor: colors.brandTertiary },
                      pressed && { opacity: 0.7 },
                    ]}
                    testID={`cliente-form-tipo-option-${t.codigo}`}
                  >
                    <Text
                      style={[
                        styles.modalOptText,
                        sel && { color: colors.brandPrimary, fontWeight: "500" },
                      ]}
                    >
                      {t.descricao}
                    </Text>
                    {sel ? (
                      <Ionicons name="checkmark" size={18} color={colors.brandPrimary} />
                    ) : null}
                  </Pressable>
                );
              })}
              {f.tiposCliente.length === 0 ? (
                <Text style={[styles.modalOptText, { padding: spacing.lg, color: colors.muted }]}>
                  Nenhum tipo cadastrado.
                </Text>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {f.toastMsg ? (
        <View
          style={[
            styles.toast,
            TOAST_SHADOW_STYLE,
            { backgroundColor: toastBackgroundColor(f.toastTone) },
          ]}
          testID="cliente-form-toast"
        >
          <Text style={styles.toastText}>{f.toastMsg}</Text>
        </View>
      ) : null}
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
  iconBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  headerLogo: {
    width: 56,
    height: 16,
    marginRight: 8,
  },
  headerTitle: {
    flex: 1, color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)",
    minWidth: 90, justifyContent: "center",
  },
  saveLabel: {
    color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxxl,
  },
  scrollWeb: {
    alignItems: "center",
  },
  sectionTitle: {
    fontSize: 14, fontWeight: "500", color: colors.onSurface,
    marginTop: spacing.md, marginBottom: spacing.sm,
    textTransform: "uppercase", letterSpacing: 0.5,
  },
  sectionHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginTop: spacing.md, marginBottom: spacing.sm,
  },
  sectionHeaderWeb: {
    width: "100%",
    maxWidth: 1080,
    alignSelf: "center",
  },
  sectionHeaderCompactWeb: {
    width: "100%",
    maxWidth: 920,
    alignSelf: "center",
  },
  sectionTitleCompactWeb: {
    width: "100%",
    maxWidth: 920,
    alignSelf: "center",
  },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.md,
  },
  cardWeb: {
    width: "100%",
    maxWidth: 1080,
    alignSelf: "center",
  },
  cardCompactWeb: {
    width: "100%",
    maxWidth: 920,
    alignSelf: "center",
  },
  formGridWeb: {
    flexDirection: "row",
    flexWrap: "wrap",
    columnGap: spacing.md,
  },
  colHalf: {
    width: "49%",
  },
  fullWidth: {
    width: "100%",
  },
  fieldLabel: {
    fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500",
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  dropdown: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: 0, minHeight: 40,
  },
  dropdownText: { flex: 1, color: colors.onSurface, fontSize: 14 },
  switchRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: 6, marginTop: 4,
  },
  switchRowWeb: {
    justifyContent: "flex-start",
    gap: 12,
  },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  hint: {
    fontSize: 12, color: colors.muted, marginTop: spacing.sm, fontStyle: "italic",
  },
  telRow: {
    flexDirection: "row", alignItems: "flex-end", gap: 8,
    marginBottom: spacing.md,
  },
  delBtn: {
    width: 38, height: 38, alignItems: "center", justifyContent: "center",
    borderRadius: radius.sm,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  addBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.brandPrimary,
  },
  addBtnText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 13 },
  radioRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: spacing.md,
  },
  radioBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  radioBtnSel: {
    borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary,
  },
  radioCircle: {
    width: 16, height: 16, borderRadius: 8,
    borderWidth: 1.5, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: {
    width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary,
  },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  inputWithBtn: { flexDirection: "row", alignItems: "center", minWidth: 0 },
  enderecoRowWeb: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
  },
  enderecoCepColWeb: {
    width: 230,
    minWidth: 0,
  },
  enderecoMainColWeb: {
    flex: 1,
    minWidth: 0,
  },
  enderecoCompColWeb: {
    flex: 1.2,
  },
  enderecoBairroColWeb: {
    flex: 1.1,
  },
  enderecoCidadeColWeb: {
    flex: 1,
  },
  enderecoUfColWeb: {
    width: 86,
  },
  cepBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
    borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    marginLeft: 8,
  },
  row2: { flexDirection: "row", gap: 8 },
  modalBackdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center", justifyContent: "center", padding: spacing.lg,
  },
  modalCard: {
    width: "100%", maxWidth: 420,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  modalTitle: {
    fontSize: 16, fontWeight: "500", color: colors.onSurface,
    marginBottom: spacing.md,
  },
  modalOpt: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.md, paddingVertical: 12,
    borderRadius: radius.sm,
  },
  modalOptText: { color: colors.onSurface, fontSize: 14 },
  toast: {
    position: "absolute",
    left: spacing.lg, right: spacing.lg,
    top: "45%",
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: "center",
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
});
