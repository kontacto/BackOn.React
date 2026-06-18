import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
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
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

// ---------- Tipos ----------
type TipoCliente = { codigo: number; descricao: string };
type Telefone = { ddd: string; tel: string; descricao: string };
type Endereco = {
  tipo: number; // 0=Comercial, 1=Cobrança, 2=Entrega
  cep: string;
  endereco: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
};

const ENDERECO_TIPOS = [
  { value: 0, label: "Comercial" },
  { value: 1, label: "Cobrança" },
  { value: 2, label: "Entrega" },
];

// ---------- Validação CPF/CNPJ (espelha backend) ----------
function onlyAlnumUpper(s: string): string {
  return (s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function validCPF(s: string): boolean {
  const d = s.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  for (const len of [9, 10]) {
    let sum = 0;
    for (let j = 0; j < len; j++) sum += parseInt(d[j], 10) * (len + 1 - j);
    let dv = (sum * 10) % 11;
    if (dv === 10) dv = 0;
    if (dv !== parseInt(d[len], 10)) return false;
  }
  return true;
}

function validCNPJ(s: string): boolean {
  const v = onlyAlnumUpper(s);
  if (v.length !== 14) return false;
  if (!/^[A-Z0-9]{12}\d{2}$/.test(v)) return false;
  if (new Set(v.split("")).size === 1) return false;
  const val = (c: string) => c.charCodeAt(0) - "0".charCodeAt(0);
  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let s1 = 0;
  for (let i = 0; i < 12; i++) s1 += val(v[i]) * p1[i];
  let dv1 = s1 % 11;
  dv1 = dv1 < 2 ? 0 : 11 - dv1;
  if (dv1 !== parseInt(v[12], 10)) return false;
  let s2 = 0;
  for (let i = 0; i < 13; i++) s2 += val(v[i]) * p2[i];
  let dv2 = s2 % 11;
  dv2 = dv2 < 2 ? 0 : 11 - dv2;
  if (dv2 !== parseInt(v[13], 10)) return false;
  return true;
}

function detectDocType(raw: string): "CPF" | "CNPJ" | "UNKNOWN" {
  const v = onlyAlnumUpper(raw);
  if (v.length === 0) return "UNKNOWN";
  if (/[A-Z]/.test(v)) return "CNPJ";
  if (v.length <= 11) return "CPF";
  return "CNPJ";
}

function maskCgcCpf(raw: string): string {
  const v = onlyAlnumUpper(raw).slice(0, 14);
  const tipo = detectDocType(v);
  if (tipo === "CPF") {
    // 000.000.000-00
    return v
      .slice(0, 11)
      .replace(/^(\d{0,3})(\d{0,3})?(\d{0,3})?(\d{0,2})?.*/, (_m, a, b, c, d) => {
        let out = a;
        if (b) out += "." + b;
        if (c) out += "." + c;
        if (d) out += "-" + d;
        return out;
      });
  }
  // CNPJ (numérico ou alfanumérico): XX.XXX.XXX/XXXX-DD
  const padded = v.padEnd(14, " ").slice(0, 14);
  let out = "";
  for (let i = 0; i < v.length; i++) {
    if (i === 2 || i === 5) out += ".";
    if (i === 8) out += "/";
    if (i === 12) out += "-";
    out += padded[i];
  }
  return out;
}

function emailValido(s: string): boolean {
  if (!s) return true; // opcional
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());
}

// ---------- Toast simples ----------
function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const [tone, setTone] = useState<"info" | "error" | "success">("info");
  const tRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback(
    (m: string, t: "info" | "error" | "success" = "info") => {
      setMsg(m);
      setTone(t);
      if (tRef.current) clearTimeout(tRef.current);
      tRef.current = setTimeout(() => setMsg(null), 3500);
    },
    []
  );
  const node = msg ? (
    <View
      style={[
        styles.toast,
        tone === "error" && { backgroundColor: colors.error },
        tone === "success" && { backgroundColor: colors.success },
      ]}
      testID="cliente-form-toast"
    >
      <Text style={styles.toastText}>{msg}</Text>
    </View>
  ) : null;
  return { show, node };
}

// ============================================================
// Tela
// ============================================================
export default function ClienteFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const editing = !!params.codigo;
  const codigo = params.codigo ? parseInt(String(params.codigo), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [vendedor, setVendedor] = useState<number | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const { show: showToast, node: toastNode } = useToast();

  // Dados principais
  const [cgcCpf, setCgcCpf] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [inscre, setInscre] = useState("");
  const [tipo, setTipo] = useState<string>(""); // codigo string FK
  const [aceitaEmail, setAceitaEmail] = useState(false);

  // Tipos disponíveis
  const [tiposCliente, setTiposCliente] = useState<TipoCliente[]>([]);
  const [tipoModalVisible, setTipoModalVisible] = useState(false);

  // Telefones (até 3)
  const [telefones, setTelefones] = useState<Telefone[]>([
    { ddd: "", tel: "", descricao: "" },
  ]);

  // Endereço (1)
  const [endereco, setEndereco] = useState<Endereco>({
    tipo: 0,
    cep: "",
    endereco: "",
    numero: "",
    complemento: "",
    bairro: "",
    cidade: "",
    uf: "",
  });
  const [cepLoading, setCepLoading] = useState(false);

  // -------- Init: carrega conexão, vendedor, tipos, e (se editando) cliente
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const session = await getSession();
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === session?.empresa) || null;
      if (cancelled) return;
      if (!c) {
        showToast("Conexão não encontrada.", "error");
        setLoadingInit(false);
        return;
      }
      setConn(c);

      const codInt = session?.funcionario?.codigo_int;
      if (typeof codInt === "number") setVendedor(codInt);
      else if (typeof codInt === "string" && /^\d+$/.test(codInt)) setVendedor(parseInt(codInt, 10));

      // Carrega dropdown tipo_cliente
      try {
        const url = `${c.api.replace(/\/+$/, "")}/api/tipo-cliente?servidor=${encodeURIComponent(
          c.servidor
        )}&banco=${encodeURIComponent(c.banco)}`;
        const r = await fetch(url);
        const j = await r.json();
        if (!cancelled && j?.success && Array.isArray(j.items)) {
          setTiposCliente(j.items as TipoCliente[]);
        } else if (!cancelled) {
          showToast(j?.message || "Falha ao carregar tipos de cliente.", "error");
        }
      } catch (e) {
        if (!cancelled)
          showToast(`Erro ao carregar tipos: ${e instanceof Error ? e.message : e}`, "error");
      }

      // Se editando, carrega cliente
      if (editing && codigo) {
        try {
          const url = `${c.api.replace(/\/+$/, "")}/api/clientes/${codigo}?servidor=${encodeURIComponent(
            c.servidor
          )}&banco=${encodeURIComponent(c.banco)}`;
          const r = await fetch(url);
          const j = await r.json();
          if (cancelled) return;
          if (!j?.success) {
            showToast(j?.message || "Erro ao carregar cliente.", "error");
          } else {
            const cli = j.cliente || {};
            setCgcCpf(maskCgcCpf(cli.cgc_cpf || ""));
            setNome(cli.nome || "");
            setEmail(cli.e_mail || "");
            setInscre(cli.inscre || "");
            setTipo(cli.tipo ? String(cli.tipo).trim() : "");
            setAceitaEmail(!!cli.aceita_email);

            // Endereço
            if (j.endereco) {
              setEndereco({
                tipo: typeof j.endereco.tipo === "number" ? j.endereco.tipo : 0,
                cep: j.endereco.cep || "",
                endereco: j.endereco.endereco || "",
                numero: j.endereco.numero != null ? String(j.endereco.numero) : "",
                complemento: j.endereco.complemento || "",
                bairro: j.endereco.bairro || "",
                cidade: j.endereco.cidade || "",
                uf: j.endereco.uf || "",
              });
            }

            // Telefones (puxa de cliente_tel; se vazio mas cliente tem ddd_cli/telefone_cli, usa esses)
            const tels: Telefone[] = Array.isArray(j.telefones)
              ? j.telefones.map((t: { ddd?: string; tel?: string; descricao?: string }) => ({
                  ddd: t.ddd || "",
                  tel: t.tel || "",
                  descricao: t.descricao || "",
                }))
              : [];
            if (tels.length === 0 && (cli.ddd_cli || cli.telefone_cli)) {
              tels.push({
                ddd: cli.ddd_cli || "",
                tel: cli.telefone_cli || "",
                descricao: "Principal",
              });
            }
            if (tels.length === 0) tels.push({ ddd: "", tel: "", descricao: "" });
            setTelefones(tels);
          }
        } catch (e) {
          if (!cancelled)
            showToast(`Erro ao carregar: ${e instanceof Error ? e.message : e}`, "error");
        }
      }

      if (!cancelled) setLoadingInit(false);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------- Label dinâmico do campo "inscre"
  const docType = useMemo(() => detectDocType(cgcCpf), [cgcCpf]);
  const labelInscre = docType === "CPF" ? "Identidade" : "Insc. Estadual";

  // -------- Tipo cliente selecionado (descrição para exibir)
  const tipoSelecionadoLabel = useMemo(() => {
    if (!tipo) return "";
    const t = tiposCliente.find((x) => String(x.codigo) === tipo);
    return t ? t.descricao : `Código ${tipo}`;
  }, [tipo, tiposCliente]);

  // -------- ViaCEP
  const buscarCEP = useCallback(
    async (cepRaw: string) => {
      const cep = cepRaw.replace(/\D/g, "").slice(0, 8);
      if (cep.length !== 8) return;
      setCepLoading(true);
      try {
        const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const j = await r.json();
        if (j?.erro) {
          showToast("CEP não encontrado.", "error");
        } else {
          setEndereco((prev) => ({
            ...prev,
            cep,
            endereco: j.logradouro || prev.endereco,
            bairro: j.bairro || prev.bairro,
            cidade: j.localidade || prev.cidade,
            uf: (j.uf || prev.uf || "").toUpperCase().slice(0, 2),
          }));
        }
      } catch (e) {
        showToast(`Falha ViaCEP: ${e instanceof Error ? e.message : e}`, "error");
      } finally {
        setCepLoading(false);
      }
    },
    [showToast]
  );

  // -------- Handlers
  const handleCgcCpfChange = (txt: string) => {
    setCgcCpf(maskCgcCpf(txt));
  };

  const handleCepChange = (txt: string) => {
    const d = txt.replace(/\D/g, "").slice(0, 8);
    setEndereco((prev) => ({ ...prev, cep: d }));
    if (d.length === 8) buscarCEP(d);
  };

  const addTelefone = () => {
    if (telefones.length >= 3) {
      showToast("Máximo de 3 telefones.", "info");
      return;
    }
    setTelefones((prev) => [...prev, { ddd: "", tel: "", descricao: "" }]);
  };

  const removeTelefone = (idx: number) => {
    setTelefones((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length === 0 ? [{ ddd: "", tel: "", descricao: "" }] : next;
    });
  };

  const updateTelefone = (idx: number, patch: Partial<Telefone>) => {
    setTelefones((prev) => prev.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  };

  // -------- Validações pré-save
  const validateAll = (): string | null => {
    if (!nome.trim()) return "Nome é obrigatório.";
    if (nome.trim().length > 60) return "Nome excede 60 caracteres.";
    const raw = onlyAlnumUpper(cgcCpf);
    if (raw) {
      if (raw.length === 11) {
        if (!validCPF(raw)) return "CPF inválido.";
      } else if (raw.length === 14) {
        if (!validCNPJ(raw)) return "CNPJ inválido.";
      } else {
        return "CGC/CPF deve ter 11 (CPF) ou 14 (CNPJ) caracteres.";
      }
    }
    if (!emailValido(email)) return "E-mail inválido.";
    if (endereco.uf && endereco.uf.trim().length !== 2)
      return "UF deve ter 2 caracteres.";
    if (endereco.cep && endereco.cep.replace(/\D/g, "").length !== 8)
      return "CEP deve ter 8 dígitos.";
    const telsValidos = telefones.filter((t) => (t.tel || "").trim().length > 0);
    for (const t of telsValidos) {
      if (!/^\d{0,4}$/.test((t.ddd || "").trim())) return "DDD inválido (até 4 dígitos).";
    }
    return null;
  };

  // -------- Gravar
  const handleSave = async () => {
    const err = validateAll();
    if (err) {
      showToast(err, "error");
      return;
    }
    if (!conn) {
      showToast("Conexão indisponível.", "error");
      return;
    }
    setSaving(true);
    try {
      const telsToSend = telefones
        .filter((t) => (t.tel || "").trim().length > 0)
        .slice(0, 3)
        .map((t) => ({
          ddd: (t.ddd || "").trim(),
          tel: (t.tel || "").trim(),
          descricao: (t.descricao || "").trim(),
        }));

      const enderecoToSend =
        endereco.cep || endereco.endereco || endereco.cidade
          ? {
              tipo: endereco.tipo,
              cep: endereco.cep.replace(/\D/g, ""),
              endereco: endereco.endereco.trim(),
              numero: endereco.numero ? parseInt(endereco.numero, 10) || null : null,
              complemento: endereco.complemento.trim(),
              bairro: endereco.bairro.trim(),
              cidade: endereco.cidade.trim(),
              uf: endereco.uf.trim().toUpperCase(),
            }
          : null;

      const body = {
        servidor: conn.servidor,
        banco: conn.banco,
        cgc_cpf: onlyAlnumUpper(cgcCpf),
        nome: nome.trim(),
        e_mail: email.trim(),
        inscre: inscre.trim(),
        tipo: tipo,
        aceita_email: aceitaEmail,
        vendedor: vendedor,
        usuario_cadastro: vendedor,
        usuario_alteracao: vendedor,
        endereco: enderecoToSend,
        telefones: telsToSend,
      };

      const base = conn.api.replace(/\/+$/, "");
      const url = editing && codigo ? `${base}/api/clientes/${codigo}` : `${base}/api/clientes/create`;
      const method = editing && codigo ? "PUT" : "POST";

      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else {
        showToast(editing ? "Cliente atualizado." : "Cliente cadastrado.", "success");
        setTimeout(() => router.back(), 700);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loadingInit) {
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
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Cliente #${codigo}` : "Novo Cliente"}
        </Text>
        <Pressable
          onPress={handleSave}
          disabled={saving}
          style={({ pressed }) => [
            styles.saveBtn,
            (pressed || saving) && { opacity: 0.7 },
          ]}
          hitSlop={8}
          testID="cliente-form-save-button"
        >
          {saving ? (
            <ActivityIndicator color={colors.onBrandPrimary} size="small" />
          ) : (
            <>
              <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Gravar</Text>
            </>
          )}
        </Pressable>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 0}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ============ Dados Principais ============ */}
          <Text style={styles.sectionTitle}>Dados Principais</Text>
          <View style={styles.card}>
            <Field label={`CGC/CPF ${docType === "UNKNOWN" ? "" : `(${docType})`}`}>
              <TextInput
                value={cgcCpf}
                onChangeText={handleCgcCpfChange}
                placeholder="CPF (11) ou CNPJ (14, aceita letras)"
                placeholderTextColor={colors.muted}
                style={styles.input}
                autoCapitalize="characters"
                testID="cliente-form-cgc-cpf-input"
              />
            </Field>

            <Field label="Nome / Razão Social *">
              <TextInput
                value={nome}
                onChangeText={setNome}
                placeholder="Nome do cliente"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={60}
                testID="cliente-form-nome-input"
              />
            </Field>

            <Field label="E-mail">
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="email@dominio.com"
                placeholderTextColor={colors.muted}
                style={styles.input}
                keyboardType="email-address"
                autoCapitalize="none"
                testID="cliente-form-email-input"
              />
            </Field>

            <Field label={labelInscre}>
              <TextInput
                value={inscre}
                onChangeText={setInscre}
                placeholder={labelInscre}
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={18}
                testID="cliente-form-inscre-input"
              />
            </Field>

            <Field label="Tipo Cliente">
              <Pressable
                onPress={() => setTipoModalVisible(true)}
                style={({ pressed }) => [styles.input, styles.dropdown, pressed && { opacity: 0.7 }]}
                testID="cliente-form-tipo-dropdown"
              >
                <Text
                  style={[
                    styles.dropdownText,
                    !tipoSelecionadoLabel && { color: colors.muted },
                  ]}
                  numberOfLines={1}
                >
                  {tipoSelecionadoLabel || "Selecione…"}
                </Text>
                <Ionicons name="chevron-down" size={16} color={colors.muted} />
              </Pressable>
            </Field>

            <View style={styles.switchRow}>
              <Text style={styles.switchLabel}>Aceita receber e-mail</Text>
              <Switch
                value={aceitaEmail}
                onValueChange={setAceitaEmail}
                trackColor={{ false: colors.border, true: colors.brandSecondary }}
                thumbColor={aceitaEmail ? colors.brandPrimary : "#f4f3f4"}
                testID="cliente-form-aceita-email-switch"
              />
            </View>

            {vendedor != null ? (
              <Text style={styles.hint} testID="cliente-form-vendedor-hint">
                Vendedor: #{vendedor}
              </Text>
            ) : (
              <Text style={[styles.hint, { color: colors.warning }]}>
                Aviso: vendedor não identificado na sessão.
              </Text>
            )}
          </View>

          {/* ============ Telefones ============ */}
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Telefones</Text>
            <Pressable
              onPress={addTelefone}
              disabled={telefones.length >= 3}
              style={({ pressed }) => [
                styles.addBtn,
                (pressed || telefones.length >= 3) && { opacity: 0.5 },
              ]}
              testID="cliente-form-add-telefone-button"
            >
              <Ionicons name="add" size={16} color={colors.brandPrimary} />
              <Text style={styles.addBtnText}>Adicionar</Text>
            </Pressable>
          </View>
          <View style={styles.card}>
            {telefones.map((t, idx) => (
              <View key={idx} style={styles.telRow} testID={`cliente-form-telefone-${idx}`}>
                <View style={{ width: 64 }}>
                  <Text style={styles.fieldLabel}>DDD</Text>
                  <TextInput
                    value={t.ddd}
                    onChangeText={(v) =>
                      updateTelefone(idx, { ddd: v.replace(/\D/g, "").slice(0, 4) })
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
                      updateTelefone(idx, { tel: v.replace(/\D/g, "").slice(0, 10) })
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
                    onChangeText={(v) => updateTelefone(idx, { descricao: v })}
                    style={styles.input}
                    placeholder="Comercial"
                    placeholderTextColor={colors.muted}
                    testID={`cliente-form-telefone-${idx}-desc`}
                  />
                </View>
                {telefones.length > 1 ? (
                  <Pressable
                    onPress={() => removeTelefone(idx)}
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
          <Text style={styles.sectionTitle}>Endereço</Text>
          <View style={styles.card}>
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

            <Field label="CEP">
              <View style={styles.inputWithBtn}>
                <TextInput
                  value={endereco.cep}
                  onChangeText={handleCepChange}
                  style={[styles.input, { flex: 1 }]}
                  keyboardType="number-pad"
                  maxLength={8}
                  placeholder="00000000"
                  placeholderTextColor={colors.muted}
                  testID="cliente-form-endereco-cep"
                />
                {cepLoading ? (
                  <ActivityIndicator
                    color={colors.brandPrimary}
                    style={{ marginLeft: 8 }}
                  />
                ) : (
                  <Pressable
                    onPress={() => buscarCEP(endereco.cep)}
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
                  setTipo("");
                  setTipoModalVisible(false);
                }}
                style={({ pressed }) => [styles.modalOpt, pressed && { opacity: 0.7 }]}
              >
                <Text style={[styles.modalOptText, { color: colors.muted }]}>
                  (Nenhum)
                </Text>
              </Pressable>
              {tiposCliente.map((t) => {
                const sel = String(t.codigo) === tipo;
                return (
                  <Pressable
                    key={t.codigo}
                    onPress={() => {
                      setTipo(String(t.codigo));
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
              {tiposCliente.length === 0 ? (
                <Text style={[styles.modalOptText, { padding: spacing.lg, color: colors.muted }]}>
                  Nenhum tipo cadastrado.
                </Text>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {toastNode}
    </SafeAreaView>
  );
}

// ---------- Componente auxiliar Field ----------
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: spacing.md }}>
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
  sectionTitle: {
    fontSize: 14, fontWeight: "500", color: colors.onSurface,
    marginTop: spacing.md, marginBottom: spacing.sm,
    textTransform: "uppercase", letterSpacing: 0.5,
  },
  sectionHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginTop: spacing.md, marginBottom: spacing.sm,
  },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.md,
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
  inputWithBtn: { flexDirection: "row", alignItems: "center" },
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
    position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.xl,
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderRadius: radius.md,
    shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 8, shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "500" },
});
