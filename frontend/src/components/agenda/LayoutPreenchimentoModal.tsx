// Preenchimento de Formulário Dinâmico (Motor de Layout — `FrmPreLay2.frm`,
// lógica comentada usada como especificação funcional, ver
// backend/services/layout_service.py e PENDENCIAS.md > "Motor de Layout").
// Reaproveitável por qualquer entidade (hoje só Agenda usa, `entidade=8`) —
// basta passar `entidade`/`codentidade` diferentes.
//
// Escopo desta rodada (decisão registrada em PENDENCIAS.md): só o modo
// "grade de campos" em texto livre — sem resolução ao vivo de campo
// calculado (soma/subtração/multiplicação/divisão entre 2 campos), sem
// impressão do preenchimento, sem comparação entre preenchimentos. Campo
// calculado aparece desabilitado com um aviso, em vez de tentar calcular
// errado.
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { styles } from "@/src/components/pedido/styles";

const isWeb = Platform.OS === "web";

type LayoutOpt = { codigo: number; descricao: string };
type Preenchido = { codigo: number; descricao: string; data: string };
type Campo = {
  codigo: number; campo1: string; campo2: string; tipo_descricao: string;
  calculado: boolean; unidade_medida: string; conteudo?: string;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  entidade: number;
  codentidade: number;
  usuarioCod: number;
  title?: string;
};

export default function LayoutPreenchimentoModal({
  visible, onClose, conn, entidade, codentidade, usuarioCod, title,
}: Props) {
  const feedback = useFeedback();
  const [loading, setLoading] = useState(false);
  const [possiveis, setPossiveis] = useState<LayoutOpt[]>([]);
  const [preenchidos, setPreenchidos] = useState<Preenchido[]>([]);

  // Formulário aberto pra preencher/editar — codlayout + código de
  // layout_entidade (null = novo preenchimento).
  const [formLayout, setFormLayout] = useState<{ codlayout: number; codigo: number | null; descricao: string } | null>(null);
  const [campos, setCampos] = useState<Campo[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!visible || !conn) return;
    setFormLayout(null);
    setLoading(true);
    Promise.all([
      apiGet(conn, "/api/layout/possiveis", { entidade, codentidade }),
      apiGet(conn, "/api/layout/preenchidos", { entidade, codentidade }),
    ])
      .then(([jp, jh]) => {
        setPossiveis(jp?.success ? jp.items || [] : []);
        setPreenchidos(jh?.success ? jh.items || [] : []);
      })
      .finally(() => setLoading(false));
  }, [visible, conn, entidade, codentidade]);

  const abrirNovo = async (l: LayoutOpt) => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/layout/campos", { layout: l.codigo });
      const items: Campo[] = (j?.success ? j.items || [] : []).map((c: Campo) => ({ ...c, conteudo: "" }));
      setCampos(items);
      setFormLayout({ codlayout: l.codigo, codigo: null, descricao: l.descricao });
    } finally {
      setLoading(false);
    }
  };

  const abrirPreenchido = async (p: Preenchido) => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, `/api/layout/preenchimento/${p.codigo}`);
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao carregar preenchimento.")); return; }
      setCampos(j.campos || []);
      setFormLayout({ codlayout: j.codlayout, codigo: j.codigo, descricao: p.descricao });
    } finally {
      setLoading(false);
    }
  };

  const setConteudo = (codigoCampo: number, v: string) => {
    setCampos((prev) => prev.map((c) => (c.codigo === codigoCampo ? { ...c, conteudo: v } : c)));
  };

  const salvar = async () => {
    if (!conn || !formLayout) return;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/layout/preencher", "POST", {
        entidade, codentidade, codlayout: formLayout.codlayout, codigo: formLayout.codigo,
        usuario_alteracao: usuarioCod,
        respostas: campos
          .filter((c) => !c.calculado && (c.conteudo || "").trim())
          .map((c) => ({ codigo_campo: c.codigo, conteudo: c.conteudo || "" })),
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao gravar preenchimento.")); return; }
      feedback.showSuccess("Preenchimento gravado.");
      setFormLayout(null);
      const jh = await apiGet(conn, "/api/layout/preenchidos", { entidade, codentidade });
      setPreenchidos(jh?.success ? jh.items || [] : []);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gravar preenchimento."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>
              {formLayout ? formLayout.descricao : (title || "Formulários (Layouts)")}
            </Text>
            <Pressable onPress={formLayout ? () => setFormLayout(null) : onClose} hitSlop={8}>
              <Ionicons name={formLayout ? "arrow-back" : "close"} size={22} color={colors.muted} />
            </Pressable>
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          {!loading && !formLayout ? (
            <ScrollView style={{ maxHeight: 420 }}>
              {possiveis.length > 0 ? (
                <>
                  <Text style={styles.itensHintText}>Preencher novo</Text>
                  {possiveis.map((l) => (
                    <Pressable
                      key={l.codigo}
                      onPress={() => abrirNovo(l)}
                      style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                      testID={`layout-possivel-${l.codigo}`}
                    >
                      <Ionicons name="document-text-outline" size={16} color={colors.brandPrimary} />
                      <Text style={styles.resultNome}>{l.descricao}</Text>
                    </Pressable>
                  ))}
                </>
              ) : null}
              <Text style={[styles.itensHintText, { marginTop: spacing.md }]}>Preenchidos anteriormente</Text>
              {preenchidos.length === 0 ? (
                <Text style={styles.resultSub}>Nenhum preenchimento ainda.</Text>
              ) : (
                preenchidos.map((p) => (
                  <Pressable
                    key={p.codigo}
                    onPress={() => abrirPreenchido(p)}
                    style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`layout-preenchido-${p.codigo}`}
                  >
                    <Ionicons name="document-outline" size={16} color={colors.muted} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.resultNome}>{p.descricao}</Text>
                      <Text style={styles.resultSub}>{p.data}</Text>
                    </View>
                  </Pressable>
                ))
              )}
              {possiveis.length === 0 && preenchidos.length === 0 ? (
                <Text style={styles.resultSub}>Nenhum layout aplicável a este registro.</Text>
              ) : null}
            </ScrollView>
          ) : null}

          {!loading && formLayout ? (
            <ScrollView style={{ maxHeight: 420 }}>
              <View style={{ gap: spacing.sm }}>
                {campos.map((c) => (
                  <View key={c.codigo}>
                    <Text style={styles.fieldLabel}>
                      {c.campo1}{c.campo2 ? ` — ${c.campo2}` : ""}{c.unidade_medida ? ` (${c.unidade_medida})` : ""}
                    </Text>
                    {c.calculado ? (
                      <Text style={[styles.resultSub, { fontStyle: "italic" }]}>
                        Campo calculado — resolvido a partir de outros campos (sem edição direta).
                      </Text>
                    ) : (
                      <TextInput
                        value={c.conteudo || ""}
                        onChangeText={(v) => setConteudo(c.codigo, v)}
                        style={styles.input}
                        placeholder={c.tipo_descricao}
                        placeholderTextColor={colors.muted}
                        testID={`layout-campo-${c.codigo}`}
                      />
                    )}
                  </View>
                ))}
                {campos.length === 0 ? (
                  <Text style={styles.resultSub}>Este layout não tem campos cadastrados.</Text>
                ) : null}
                <View style={styles.modalBtns}>
                  <Pressable onPress={() => setFormLayout(null)} style={[styles.secondaryBtn, { flex: 1, alignItems: "center" }]}>
                    <Text style={styles.secondaryBtnText}>Voltar</Text>
                  </Pressable>
                  <Pressable
                    onPress={salvar}
                    disabled={saving}
                    style={[styles.primaryBtn, { flex: 1, opacity: saving ? 0.7 : 1 }]}
                    testID="layout-preencher-salvar"
                  >
                    {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
