// Card de um equipamento vinculado à O.S. (Assistência Técnica, regra 14 —
// ver useOSEquipamentos.ts). Mantém um rascunho local dos campos de talão
// (Defeito Reclamado/Serviço Executado/Serviço a Executar/Diagnóstico) +
// Status do equipamento, gravado com um botão "Salvar" próprio da linha —
// diferente do cabeçalho da OS (que salva tudo junto no "Gravar" do topo),
// já que cada equipamento é uma linha independente na tabela `os_equipamento`.
import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "@/src/theme/colors";
import { Ionicons } from "@/src/components/Ionicons";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { OSEquipamentoRow } from "./types";
import { OSEquipamentoDraft } from "./useOSEquipamentos";

type Props = {
  item: OSEquipamentoRow;
  statusOptions: SelectOption[];
  editavel: boolean;
  canCancelar: boolean;
  saving: boolean;
  canceling: boolean;
  onSalvar: (draft: OSEquipamentoDraft) => void;
  onCancelar: () => void;
};

export default function OSEquipamentoCard({
  item, statusOptions, editavel, canCancelar, saving, canceling, onSalvar, onCancelar,
}: Props) {
  const [defeito, setDefeito] = useState(item.defeito_reclamado);
  const [servicoExecutado, setServicoExecutado] = useState(item.servico_executado);
  const [servicoAExecutar, setServicoAExecutar] = useState(item.servico_a_executar);
  const [diagnostico, setDiagnostico] = useState(item.diagnostico);
  const [statusOs, setStatusOs] = useState<number | null>(item.status_os);
  // Accordion — cada equipamento nasce aberto (não regride o caso comum de
  // 1 só equipamento), mas recolhe pra não consumir a tela toda quando a OS
  // tem vários (user-directed, 2026-08-13, "cada equipamento tem que ter
  // accordion"). Cabeçalho é um `Pressable` separado do botão Cancelar
  // (irmãos, não aninhados) pra evitar bubbling de clique no web.
  const [expanded, setExpanded] = useState(true);

  const salvar = () => onSalvar({
    defeito_reclamado: defeito, servico_executado: servicoExecutado,
    servico_a_executar: servicoAExecutar, diagnostico, status_os: statusOs,
  });

  return (
    <View style={s.card} testID={`os-equipamento-card-${item.codigo}`}>
      <View style={s.header}>
        <Pressable
          onPress={() => setExpanded((v) => !v)}
          style={{ flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: 6 }}
          testID={`os-equipamento-toggle-${item.codigo}`}
        >
          <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={s.titulo} numberOfLines={1}>
              {item.numero_de_serie}
              {item.marca_descricao ? ` · ${item.marca_descricao}` : ""}
              {item.modelo_descricao ? ` ${item.modelo_descricao}` : ""}
            </Text>
            {item.principal ? <Text style={s.principalTag}>Equipamento original da O.S.</Text> : null}
          </View>
        </Pressable>
        {canCancelar && editavel ? (
          canceling ? (
            <ActivityIndicator color={colors.error} size="small" />
          ) : (
            <IconButtonWithTooltip
              icon="trash-outline" label="Cancelar equipamento" onPress={onCancelar}
              color={colors.error} testID={`os-equipamento-cancelar-${item.codigo}`}
            />
          )
        ) : null}
      </View>

      {expanded ? (
        <>
          <View style={s.fieldsRow}>
            <View style={s.colStatus}>
              <Text style={s.fieldLabel}>Status do equipamento</Text>
              <SelectField
                value={statusOs}
                onChange={(v) => setStatusOs(v as number | null)}
                options={statusOptions}
                compactWeb
                disabled={!editavel}
                testID={`os-equipamento-status-${item.codigo}`}
              />
            </View>
          </View>

          {/* Serviço Executado x Diagnóstico trocados de lugar
              (user-directed, 2026-08-13) — Defeito Reclamado e Serviço a
              Executar continuam nas mesmas posições. */}
          <View style={s.fieldsRow}>
            <View style={s.colHalf}>
              <Text style={s.fieldLabel}>Defeito Reclamado</Text>
              <TextInput
                value={defeito} onChangeText={setDefeito} editable={editavel} multiline
                style={[s.input, s.inputMulti]} placeholder="O que o cliente relatou"
                placeholderTextColor={colors.muted} testID={`os-equipamento-defeito-${item.codigo}`}
              />
            </View>
            <View style={s.colHalf}>
              <Text style={s.fieldLabel}>Diagnóstico</Text>
              <TextInput
                value={diagnostico} onChangeText={setDiagnostico} editable={editavel} multiline
                style={[s.input, s.inputMulti]} placeholder="Diagnóstico técnico"
                placeholderTextColor={colors.muted} testID={`os-equipamento-diagnostico-${item.codigo}`}
              />
            </View>
          </View>

          <View style={s.fieldsRow}>
            <View style={s.colHalf}>
              <Text style={s.fieldLabel}>Serviço a Executar</Text>
              <TextInput
                value={servicoAExecutar} onChangeText={setServicoAExecutar} editable={editavel} multiline
                style={[s.input, s.inputMulti]} placeholder="Pendente para uma próxima visita"
                placeholderTextColor={colors.muted} testID={`os-equipamento-servico-a-executar-${item.codigo}`}
              />
            </View>
            <View style={s.colHalf}>
              <Text style={s.fieldLabel}>Serviço Executado</Text>
              <TextInput
                value={servicoExecutado} onChangeText={setServicoExecutado} editable={editavel} multiline
                style={[s.input, s.inputMulti]} placeholder="O que foi executado nesta visita"
                placeholderTextColor={colors.muted} testID={`os-equipamento-servico-executado-${item.codigo}`}
              />
            </View>
          </View>

          {editavel ? (
            <View style={s.actionsRow}>
              <Pressable
                onPress={salvar} disabled={saving}
                style={[s.salvarBtn, saving && { opacity: 0.7 }]}
                testID={`os-equipamento-salvar-${item.codigo}`}
              >
                {saving ? (
                  <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                ) : (
                  <>
                    <Ionicons name="checkmark-outline" size={14} color={colors.onBrandPrimary} />
                    <Text style={s.salvarBtnText}>Salvar</Text>
                  </>
                )}
              </Pressable>
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    padding: spacing.sm, marginBottom: spacing.sm, backgroundColor: colors.surface,
  },
  header: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: spacing.xs },
  titulo: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  principalTag: { fontSize: 10, color: colors.muted, marginTop: 2 },
  // Densidade estilo VB6 (CLAUDE.md > "App Web como substituto do VB6
  // Desktop"): campos curtos/relacionados lado a lado, nunca empilhados
  // esticados a 100% — mesmo princípio de "Field Width Standard" já
  // documentado, aplicado aqui pela primeira vez neste card.
  fieldsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  colStatus: { width: 220 },
  colHalf: { flex: 1, minWidth: 200 },
  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 3, marginTop: 6, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface,
  },
  // nvarchar(500) — precisa parecer textarea de verdade, não um campo de
  // 1 linha encolhido. Regressão corrigida 2026-08-13, user-directed
  // ("campo no banco multilinha tem que refletir no cadastro") — a
  // primeira rodada de densidade tinha comprimido demais (minHeight: 36).
  inputMulti: { minHeight: 64, textAlignVertical: "top" },
  actionsRow: { flexDirection: "row", justifyContent: "flex-end", marginTop: spacing.sm },
  // Salvar por linha é uma ação inline, não de página — pill pequeno,
  // alinhado à direita, nunca full-width/dark-bar (regra já existente em
  // "Padrões de UI" > 3, reforçada aqui: botão nunca esticado sozinho).
  salvarBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingVertical: 6, paddingHorizontal: 14,
  },
  salvarBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 12 },
});
