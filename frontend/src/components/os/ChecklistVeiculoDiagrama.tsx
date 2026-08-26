// Diagrama do Checklist de Entrada de Veículo — pedido explícito do
// usuário 2026-08-26, sem precedente no legado/no resto do projeto: toca
// no diagrama pra marcar uma avaria (amassado/arranhão/quebrado/faltando/
// outro), cada toque vira UM item dinâmico (`os_checklist_veiculo`), não
// uma lista fixa de perguntas Sim/Não/Reparar.
//
// Sem precedente de captura de coordenada por toque em NENHUM lugar do
// projeto (confirmado via investigação — nem react-native-svg instalado,
// nem canvas). Como O.S. Completa já é web-only (mesmo padrão de
// WebDateField.tsx/`<input type="file">` já usados neste projeto —
// elemento HTML/SVG intrínseco do react-native-web dentro de um bloco
// `Platform.OS === "web"`), o diagrama é um `<svg>` inline, sem lib nova.
//
// Mesma silhueta simples (corpo arredondado + 4 rodas + linha do
// para-brisa marcando a frente) desenhada aqui e no PDF
// (`os_completa_pdf_service._desenhar_diagrama_veiculo`) — pra o que o
// atendente marca na tela bater visualmente com o que sai impresso.
import { useRef } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/src/theme/colors";
import { Ionicons } from "@/src/components/Ionicons";
import { OSChecklistVeiculoRow, tipoAvariaLabel } from "./types";

const isWeb = Platform.OS === "web";

const CORES_MARCA: Record<string, string> = {
  AMASSADO: "#d9534f",
  ARRANHAO: "#e0a800",
  QUEBRADO: "#c0392b",
  FALTANDO: "#8e44ad",
  OUTRO: "#607d8b",
};

type Props = {
  marcacoes: OSChecklistVeiculoRow[];
  editavel: boolean;
  onMarcar: (posX: number, posY: number) => void;
  onCancelar: (codigo: number) => void;
  cancelingCodigo: number | null;
};

const LARGURA = 320;
const ALTURA = 200;

export default function ChecklistVeiculoDiagrama({ marcacoes, editavel, onMarcar, onCancelar, cancelingCodigo }: Props) {
  const svgRef = useRef<any>(null);

  if (!isWeb) {
    return (
      <View style={s.webOnly}>
        <Text style={s.webOnlyText}>Checklist de Entrada disponível apenas na versão web desta tela.</Text>
      </View>
    );
  }

  const handleClick = (e: any) => {
    if (!editavel) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const clamp = (v: number) => Math.min(1, Math.max(0, v));
    onMarcar(clamp(x), clamp(y));
  };

  const corpoX = LARGURA * 0.12;
  const corpoLarg = LARGURA * 0.76;
  const rodaLarg = 8, rodaAlt = 22;

  return (
    <View style={s.wrap}>
      {/* eslint-disable react/no-unknown-property -- SVG intrínseco (build web), ver WebDateField.tsx pro mesmo padrão */}
      <svg
        ref={svgRef}
        width={LARGURA}
        height={ALTURA}
        viewBox={`0 0 ${LARGURA} ${ALTURA}`}
        onClick={handleClick}
        style={{ cursor: editavel ? "crosshair" : "default", touchAction: "manipulation" }}
        data-testid="checklist-veiculo-svg"
      >
        <text x={LARGURA / 2} y={12} textAnchor="middle" fontSize={10} fill={colors.muted}>FRENTE</text>
        <rect x={corpoX} y={16} width={corpoLarg} height={ALTURA - 32} rx={10} ry={10} fill="none" stroke={colors.onSurface} strokeWidth={1.5} />
        {[corpoX - 2, corpoX + corpoLarg - rodaLarg + 2].map((fx) =>
          [ALTURA * 0.16, ALTURA * 0.68].map((fyCenter) => (
            <rect key={`${fx}-${fyCenter}`} x={fx} y={fyCenter} width={rodaLarg} height={rodaAlt} fill={colors.onSurface} />
          ))
        )}
        <line x1={corpoX + 10} y1={16 + (ALTURA - 32) * 0.26} x2={corpoX + corpoLarg - 10} y2={16 + (ALTURA - 32) * 0.26} stroke={colors.border} strokeWidth={1} />

        {marcacoes.map((m, i) => {
          const px = m.pos_x * LARGURA;
          const py = m.pos_y * ALTURA;
          const cor = CORES_MARCA[m.tipo_avaria?.toUpperCase()] || CORES_MARCA.OUTRO;
          return (
            <g
              key={m.codigo}
              onClick={(e: any) => { e.stopPropagation(); if (editavel) onCancelar(m.codigo); }}
              style={{ cursor: editavel ? "pointer" : "default" }}
            >
              <circle cx={px} cy={py} r={9} fill={cor} stroke="#fff" strokeWidth={1.5} opacity={cancelingCodigo === m.codigo ? 0.4 : 1} />
              <text x={px} y={py + 3.5} textAnchor="middle" fontSize={9} fontWeight="bold" fill="#fff">{i + 1}</text>
            </g>
          );
        })}
      </svg>
      {/* eslint-enable react/no-unknown-property */}
      <Text style={s.hint}>
        {editavel ? "Toque no diagrama pra marcar uma avaria encontrada na entrada do veículo." : "Checklist só editável com a O.S. Aberta."}
      </Text>

      {marcacoes.length > 0 ? (
        <View style={s.legenda}>
          {marcacoes.map((m, i) => (
            <View key={m.codigo} style={s.legendaItem}>
              <View style={[s.legendaBolinha, { backgroundColor: CORES_MARCA[m.tipo_avaria?.toUpperCase()] || CORES_MARCA.OUTRO }]}>
                <Text style={s.legendaBolinhaTexto}>{i + 1}</Text>
              </View>
              <Text style={s.legendaTexto} numberOfLines={1}>
                {tipoAvariaLabel(m.tipo_avaria)}{m.descricao ? ` — ${m.descricao}` : ""}
              </Text>
              {editavel ? (
                <Pressable onPress={() => onCancelar(m.codigo)} disabled={cancelingCodigo === m.codigo} hitSlop={6} testID={`checklist-veiculo-cancelar-${m.codigo}`}>
                  <Ionicons name="close-circle-outline" size={16} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: "flex-start", gap: spacing.xs },
  hint: { fontSize: 11, color: colors.muted },
  webOnly: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    padding: spacing.md, backgroundColor: colors.surfaceSecondary,
  },
  webOnlyText: { fontSize: 12, color: colors.muted },
  legenda: { gap: 4, marginTop: spacing.xs, width: "100%" },
  legendaItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendaBolinha: { width: 16, height: 16, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  legendaBolinhaTexto: { fontSize: 9, fontWeight: "700", color: "#fff" },
  legendaTexto: { flex: 1, fontSize: 12, color: colors.onSurface },
});
