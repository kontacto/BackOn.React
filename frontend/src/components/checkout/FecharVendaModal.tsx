// Modal "Fechar Venda" do Checkout — lança 1+ formas de pagamento (réplica
// fiel do fechamento de FrmPafOFF.frm: Dinheiro/Cheque/Cartão Crédito/
// Cartão Débito/Duplicata/Ticket/Vale/Financiado), com validação completa de
// Administradora + Parcelador + Parcelas pra Cartão (Cartao_Verifica_
// Parcelamento, ver checkout_service.py) — decisão explícita do usuário,
// 2026-08-04. Calcula e mostra o troco quando o valor pago é maior que o
// total devido.
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { apiGet } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";
import { Connection } from "@/src/utils/storage/connections";

const isWeb = Platform.OS === "web";

export type FormaPagamentoLancada = {
  tipo: string;
  forma_pag: string;
  valor: number;
  cod_banco?: number | null;
  agencia?: number | null;
  conta?: string | null;
  numero_ch?: number | null;
  nome_cheque?: string | null;
  telefone?: string | null;
  num_cartao1?: number | null;
  num_cartao2?: number | null;
  num_cartao3?: number | null;
  num_cartao4?: number | null;
  mes_validade?: number | null;
  ano_validade?: number | null;
  parcelas?: number | null;
  cod_administradora?: number | null;
  cod_parcelador?: string | null;
};

type Row = FormaPagamentoLancada & { key: string };

const TIPOS: SelectOption[] = [
  { value: "DI", label: "Dinheiro" },
  { value: "CH", label: "Cheque" },
  { value: "CC", label: "Cartão de Crédito" },
  { value: "CD", label: "Cartão de Débito" },
  { value: "DU", label: "Duplicata / Boleto" },
  { value: "TI", label: "Ticket / Vale Refeição" },
  { value: "VA", label: "Vale" },
  { value: "FI", label: "Financiado" },
];

const PARCELADOR_OPTS: SelectOption[] = [
  { value: "L", label: "Loja" },
  { value: "A", label: "Administradora" },
];

function novaLinha(valorSugerido: number): Row {
  return { key: `${Date.now()}-${Math.random()}`, tipo: "DI", forma_pag: "", valor: valorSugerido };
}

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection;
  totalDevido: number;
  onConfirm: (formas: FormaPagamentoLancada[]) => Promise<{ success: boolean; message?: string; troco?: number }>;
};

export default function FecharVendaModal({ visible, onClose, conn, totalDevido, onConfirm }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [formasPagamento, setFormasPagamento] = useState<{ codigo: string; descricao: string; tipo: string }[]>([]);
  const [administradoras, setAdministradoras] = useState<SelectOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setRows([novaLinha(totalDevido)]);
    setErro(null);
    (async () => {
      const j = await apiGet(conn, "/api/forma-pagamento-completo");
      setFormasPagamento(j?.items || []);
      const a = await apiGet(conn, "/api/checkout/cartoes/administradoras");
      setAdministradoras((a?.items || []).map((it: any) => ({ value: it.codigo, label: it.descricao })));
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const totalLancado = useMemo(() => rows.reduce((s, r) => s + (parseFloat(String(r.valor)) || 0), 0), [rows]);
  const troco = Math.max(0, round2(totalLancado - totalDevido));
  const falta = Math.max(0, round2(totalDevido - totalLancado));

  const updateRow = (key: string, patch: Partial<Row>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, novaLinha(Math.max(0, round2(totalDevido - totalLancado)))]);
  const removeRow = (key: string) => setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.key !== key) : prev));

  const confirmar = async () => {
    setErro(null);
    if (rows.some((r) => !r.forma_pag)) {
      setErro("Selecione a forma de pagamento em todas as linhas.");
      return;
    }
    if (rows.some((r) => (r.tipo === "CC" || r.tipo === "CD") && (!r.cod_administradora || !r.cod_parcelador))) {
      setErro("Defina a administradora e o parcelador em toda linha de cartão.");
      return;
    }
    setSaving(true);
    try {
      const payload: FormaPagamentoLancada[] = rows.map(({ key, ...rest }) => rest);
      const r = await onConfirm(payload);
      if (!r.success) setErro(r.message || "Não foi possível fechar a venda.");
    } finally {
      setSaving(false);
    }
  };

  if (!visible) return null;
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact, { maxHeight: "88%" }]} onPress={(e) => e.stopPropagation()}>
          <View style={ps.modalHeader}>
            <Text style={ps.modalTitle}>Fechar Venda</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.sm }}>
            <Text style={{ fontSize: 13, color: colors.muted }}>Total a pagar</Text>
            <Text style={{ fontSize: 16, fontWeight: "700", color: colors.onSurface }}>{formatBRL(totalDevido)}</Text>
          </View>

          <ScrollView style={{ maxHeight: 420 }}>
            <View style={{ gap: spacing.md }}>
              {rows.map((row) => (
                <View
                  key={row.key}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, gap: spacing.sm }}
                >
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
                    <View style={{ flex: 1 }}>
                      <SelectField
                        label="Tipo"
                        value={row.tipo}
                        onChange={(v) => updateRow(row.key, { tipo: String(v), forma_pag: "" })}
                        options={TIPOS}
                        compactWeb
                        searchable={false}
                        testID={`fechar-tipo-${row.key}`}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <SelectField
                        label="Forma de Pagamento"
                        value={row.forma_pag || null}
                        onChange={(v) => updateRow(row.key, { forma_pag: String(v ?? "") })}
                        options={formasPagamento
                          .filter((f) => f.tipo === row.tipo)
                          .map((f) => ({ value: f.codigo, label: f.descricao }))}
                        compactWeb
                        testID={`fechar-forma-${row.key}`}
                      />
                    </View>
                    <TextInput
                      value={String(row.valor ?? "")}
                      onChangeText={(t) => updateRow(row.key, { valor: parseFloat(t.replace(",", ".")) || 0 })}
                      keyboardType="numeric"
                      placeholder="Valor"
                      placeholderTextColor={colors.muted}
                      style={{
                        width: 110, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
                        paddingHorizontal: spacing.sm, paddingVertical: 10, color: colors.onSurface,
                      }}
                      testID={`fechar-valor-${row.key}`}
                    />
                    {rows.length > 1 ? (
                      <Pressable onPress={() => removeRow(row.key)} hitSlop={8} style={{ paddingBottom: 10 }}>
                        <Ionicons name="trash-outline" size={20} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>

                  {(row.tipo === "CC" || row.tipo === "CD") ? (
                    <View style={{ flexDirection: "row", gap: spacing.sm }}>
                      <View style={{ flex: 1 }}>
                        <SelectField
                          label="Administradora"
                          value={row.cod_administradora ?? null}
                          onChange={(v) => updateRow(row.key, { cod_administradora: v == null ? null : Number(v) })}
                          options={administradoras}
                          compactWeb
                          testID={`fechar-adm-${row.key}`}
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <SelectField
                          label="Parcelador"
                          value={row.cod_parcelador ?? null}
                          onChange={(v) => updateRow(row.key, { cod_parcelador: v == null ? null : String(v) })}
                          options={PARCELADOR_OPTS}
                          compactWeb
                          searchable={false}
                          testID={`fechar-parcelador-${row.key}`}
                        />
                      </View>
                      <TextInput
                        value={String(row.parcelas ?? 1)}
                        onChangeText={(t) => updateRow(row.key, { parcelas: parseInt(t, 10) || 1 })}
                        keyboardType="numeric"
                        placeholder="Parc."
                        placeholderTextColor={colors.muted}
                        style={{
                          width: 70, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
                          paddingHorizontal: spacing.sm, paddingVertical: 10, color: colors.onSurface,
                        }}
                        testID={`fechar-parcelas-${row.key}`}
                      />
                    </View>
                  ) : null}
                </View>
              ))}

              <Pressable
                onPress={addRow}
                style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" }}
                testID="fechar-add-forma"
              >
                <Ionicons name="add-circle-outline" size={18} color={colors.brandPrimary} />
                <Text style={{ color: colors.brandPrimary, fontWeight: "600", fontSize: 13 }}>Adicionar forma de pagamento</Text>
              </Pressable>
            </View>
          </ScrollView>

          <View style={{ marginTop: spacing.md, gap: 4 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ fontSize: 13, color: colors.muted }}>Total lançado</Text>
              <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>{formatBRL(totalLancado)}</Text>
            </View>
            {falta > 0 ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ fontSize: 13, color: colors.error }}>Falta</Text>
                <Text style={{ fontSize: 13, fontWeight: "700", color: colors.error }}>{formatBRL(falta)}</Text>
              </View>
            ) : troco > 0 ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ fontSize: 13, color: colors.success }}>Troco</Text>
                <Text style={{ fontSize: 13, fontWeight: "700", color: colors.success }}>{formatBRL(troco)}</Text>
              </View>
            ) : null}
          </View>

          {erro ? <Text style={{ color: colors.error, fontSize: 13, marginTop: spacing.sm }}>{erro}</Text> : null}

          <View style={ps.modalBtns}>
            <Pressable onPress={onClose} style={ps.secondaryBtn} testID="fechar-venda-cancelar">
              <Text style={ps.secondaryBtnText}>Voltar</Text>
            </Pressable>
            <Pressable onPress={confirmar} disabled={saving} style={[ps.primaryBtn, saving && { opacity: 0.7 }]} testID="fechar-venda-confirmar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={ps.primaryBtnText}>Fechar Venda</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}
