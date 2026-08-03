// Tempo Gasto por Serviço — migração do frame "Tempo Gasto"
// (Command30_Click/Command57_Click/Command56_Click em
// Revenda\FrmTraOsNew.frm — a única cópia com essa feature de fato
// implementada, ver PENDENCIAS.md > "Tempo Gasto por Serviço"). Lança
// início/fim de atendimento por serviço + técnico dentro da O.S.
//
// Autocontido (mesmo espírito de AnexosOSModal.tsx): busca sua própria
// lista ao abrir, não depende do hook useOSItens. Combo de Serviço segue o
// mesmo fallback do legado — primeiro os serviços já lançados na O.S.
// (prop `servicosDaOS`), se vazio busca o catálogo geral de serviços.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import { apiGet, apiSend, apiDelete, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { todayISO } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type TempoItem = {
  codigo: number;
  codigo_interno: string;
  item_descricao: string;
  funcionario: number | null;
  funcionario_nome: string;
  data: string | null;
  hora_inicio: string;
  hora_fim: string | null;
  obs: string;
  tempo_gasto_min: number | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  osId: number;
  isAberto: boolean;
  funcOptions: SelectOption[];
  servicosDaOS: SelectOption[];
  classe: number | null;
  usuarioCod: number;
  onToast: (msg: string, tone: "success" | "error") => void;
};

function fmtDuracao(min: number | null): string {
  if (min == null) return "—";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

const FORM_VAZIO = { codigoInterno: null as string | number | null, funcionario: null as number | null, data: todayISO(), horaInicio: "", horaFim: "", obsTxt: "" };

export default function TempoGastoModal({ visible, onClose, conn, osId, isAberto, funcOptions, servicosDaOS, classe, usuarioCod, onToast }: Props) {
  const [items, setItems] = useState<TempoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [servOptionsFallback, setServOptionsFallback] = useState<SelectOption[]>([]);
  const [editingCodigo, setEditingCodigo] = useState<number | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);

  const servOptions = servicosDaOS.length > 0 ? servicosDaOS : servOptionsFallback;

  const load = useCallback(async () => {
    if (!conn || !osId) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, `/api/os-completo/${osId}/tempo`);
      setItems(j?.success ? (j.items || []) : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [conn, osId]);

  useEffect(() => {
    if (!visible) return;
    load();
    setEditingCodigo(null);
    setForm(FORM_VAZIO);
    if (conn && servicosDaOS.length === 0) {
      apiGet(conn, "/api/produtos-servicos", { search: "", page: 1, size: 200, tipo: "S" })
        .then((j) => {
          const opts: SelectOption[] = (j?.items || []).map((p: { codigo: string; descricao: string }) => ({ value: p.codigo, label: p.descricao }));
          setServOptionsFallback(opts);
        })
        .catch(() => setServOptionsFallback([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const startEdit = (item: TempoItem) => {
    setEditingCodigo(item.codigo);
    setForm({
      codigoInterno: item.codigo_interno, funcionario: item.funcionario,
      data: item.data || todayISO(), horaInicio: item.hora_inicio, horaFim: item.hora_fim || "",
      obsTxt: item.obs,
    });
  };

  const cancelEdit = () => { setEditingCodigo(null); setForm(FORM_VAZIO); };

  const handleSave = async () => {
    if (!conn || !osId) return;
    setSaving(true);
    try {
      const body = {
        codigo_interno: String(form.codigoInterno ?? ""), funcionario: form.funcionario,
        data: form.data, hora_inicio: form.horaInicio, hora_fim: form.horaFim || null,
        obs: form.obsTxt, classe, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      };
      const j = editingCodigo
        ? await apiSend(conn, `/api/os-completo/${osId}/tempo/${editingCodigo}`, "PUT", body)
        : await apiSend(conn, `/api/os-completo/${osId}/tempo`, "POST", body);
      if (j?.success) {
        onToast(editingCodigo ? "Tempo Gasto atualizado." : "Tempo Gasto incluído.", "success");
        cancelEdit();
        load();
      } else {
        onToast(friendlyApiError(j, "Não foi possível gravar o Tempo Gasto."), "error");
      }
    } catch (e) {
      onToast(friendlyCatchError(e, "Não foi possível gravar o Tempo Gasto."), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: TempoItem) => {
    if (!conn || !osId) return;
    setSaving(true);
    try {
      const j = await apiDelete(conn, `/api/os-completo/${osId}/tempo/${item.codigo}`, {
        classe, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        onToast("Tempo Gasto excluído.", "success");
        if (editingCodigo === item.codigo) cancelEdit();
        load();
      } else {
        onToast(friendlyApiError(j, "Não foi possível excluir o Tempo Gasto."), "error");
      }
    } catch (e) {
      onToast(friendlyCatchError(e, "Não foi possível excluir o Tempo Gasto."), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Tempo Gasto por Serviço</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              Registre o horário de início e fim do atendimento de cada serviço, por técnico. O tempo gasto é calculado automaticamente.
              {!isAberto ? " Só é possível incluir/alterar/excluir com a O.S. Aberta — aqui você só pode consultar." : ""}
            </Text>
          </View>

          {isAberto ? (
            <View style={rs.form}>
              <View style={rs.formRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Serviço</Text>
                  <SelectField
                    value={form.codigoInterno}
                    onChange={(v) => setForm((f) => ({ ...f, codigoInterno: v }))}
                    options={servOptions}
                    placeholder="Selecionar serviço"
                    modalTitle="Selecionar Serviço"
                    compactWeb
                    testID="tempo-gasto-servico"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Técnico</Text>
                  <SelectField
                    value={form.funcionario}
                    onChange={(v) => setForm((f) => ({ ...f, funcionario: v == null ? null : Number(v) }))}
                    options={funcOptions}
                    placeholder="Selecionar técnico"
                    modalTitle="Selecionar Técnico"
                    compactWeb
                    testID="tempo-gasto-tecnico"
                  />
                </View>
              </View>
              <View style={rs.formRow}>
                <View style={{ width: 150 }}>
                  <Text style={styles.fieldLabel}>Data</Text>
                  <WebDateField value={form.data} onChange={(v) => setForm((f) => ({ ...f, data: v || todayISO() }))} type="date" testID="tempo-gasto-data" />
                </View>
                <View style={{ width: 110 }}>
                  <Text style={styles.fieldLabel}>Hora Inicial</Text>
                  <WebDateField value={form.horaInicio} onChange={(v) => setForm((f) => ({ ...f, horaInicio: v }))} type="time" testID="tempo-gasto-hora-inicio" />
                </View>
                <View style={{ width: 110 }}>
                  <Text style={styles.fieldLabel}>Hora Final</Text>
                  <WebDateField value={form.horaFim} onChange={(v) => setForm((f) => ({ ...f, horaFim: v }))} type="time" testID="tempo-gasto-hora-fim" />
                </View>
              </View>
              <Text style={styles.fieldLabel}>Observação</Text>
              <TextInput
                value={form.obsTxt}
                onChangeText={(v) => setForm((f) => ({ ...f, obsTxt: v }))}
                placeholder="Observação (opcional)"
                placeholderTextColor={colors.muted}
                style={styles.input}
                testID="tempo-gasto-obs"
              />
              <View style={[styles.modalBtns, { marginTop: spacing.sm }]}>
                {editingCodigo ? (
                  <Pressable onPress={cancelEdit} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}>
                    <Text style={styles.secondaryBtnText}>Cancelar</Text>
                  </Pressable>
                ) : null}
                <Pressable
                  onPress={handleSave}
                  disabled={saving}
                  style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, (pressed || saving) && { opacity: 0.8 }]}
                  testID="tempo-gasto-salvar"
                >
                  {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>{editingCodigo ? "Salvar" : "Incluir"}</Text>}
                </Pressable>
              </View>
            </View>
          ) : null}

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
          <ScrollView style={{ maxHeight: 260, marginTop: spacing.sm }}>
            {items.map((item) => (
              <View key={item.codigo} style={rs.row}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={rs.desc} numberOfLines={1}>{item.item_descricao || item.codigo_interno}</Text>
                  <Text style={rs.sub} numberOfLines={1}>
                    {item.funcionario_nome || "—"} · {item.data ? item.data.split("-").reverse().join("/") : "—"} · {item.hora_inicio}
                    {item.hora_fim ? `–${item.hora_fim}` : ""} · {fmtDuracao(item.tempo_gasto_min)}
                  </Text>
                  {item.obs ? <Text style={rs.obs} numberOfLines={1}>{item.obs}</Text> : null}
                </View>
                {isAberto ? (
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <Pressable onPress={() => startEdit(item)} disabled={saving} hitSlop={6} testID={`tempo-gasto-editar-${item.codigo}`}>
                      <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                    </Pressable>
                    <Pressable onPress={() => handleDelete(item)} disabled={saving} hitSlop={6} testID={`tempo-gasto-excluir-${item.codigo}`}>
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  </View>
                ) : null}
              </View>
            ))}
            {!loading && items.length === 0 ? <Text style={styles.emptyText}>Nenhum lançamento de Tempo Gasto ainda.</Text> : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  form: { gap: 8, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  formRow: { flexDirection: "row" as const, gap: spacing.sm },
  row: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  desc: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface },
  sub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  obs: { fontSize: 11, color: colors.muted, marginTop: 2, fontStyle: "italic" as const },
};
