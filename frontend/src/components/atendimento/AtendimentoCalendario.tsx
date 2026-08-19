// Calendário mensal INLINE (não popup) — corpo principal da tela
// `atendimento-lista.tsx` (Lista de Atendimento por Calendário, regra 6,
// AssistenciaTecnicaCampo.md). Cross-platform (web + mobile), diferente de
// `agenda/AgendaCalendarField.tsx` (só web, formato popup ancorado a um
// campo, e com dias desabilitados por "dias que o profissional atende") —
// investigado e descartado como reaproveitável 2026-08-15: esta tela
// mostra o calendário como o conteúdo principal, sempre visível, e todo
// dia é livremente selecionável (sem conceito de disponibilidade).
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors, radius, spacing } from "@/src/theme/colors";

const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];
const DIAS_COL = ["D", "S", "T", "Q", "Q", "S", "S"];

const pad2 = (n: number) => String(n).padStart(2, "0");
const toIso = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const fromIso = (v: string) => {
  const [y, m, d] = v.split("-").map((n) => parseInt(n, 10));
  return new Date(y, (m || 1) - 1, d || 1);
};
const hojeIso = () => toIso(new Date());

type Props = {
  selecionado: string;
  onSelecionarDia: (iso: string) => void;
  testID?: string;
};

export default function AtendimentoCalendario({ selecionado, onSelecionarDia, testID }: Props) {
  const [anchor, setAnchor] = useState(() => fromIso(selecionado || hojeIso()));

  useEffect(() => {
    if (selecionado) setAnchor(fromIso(selecionado));
  }, [selecionado]);

  const ano = anchor.getFullYear();
  const mes = anchor.getMonth();
  const primeiroDoMes = new Date(ano, mes, 1);
  const inicioSemana = primeiroDoMes.getDay();
  const diasNoMes = new Date(ano, mes + 1, 0).getDate();
  const celulas: (Date | null)[] = [];
  for (let i = 0; i < inicioSemana; i++) celulas.push(null);
  for (let d = 1; d <= diasNoMes; d++) celulas.push(new Date(ano, mes, d));
  while (celulas.length % 7 !== 0) celulas.push(null);
  const semanas: (Date | null)[][] = [];
  for (let i = 0; i < celulas.length; i += 7) semanas.push(celulas.slice(i, i + 7));

  const hoje = hojeIso();
  const trocarMes = (delta: number) => setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + delta, 1));

  return (
    <View style={styles.wrap} testID={testID}>
      <View style={styles.header}>
        <Pressable onPress={() => trocarMes(-1)} hitSlop={8} style={styles.navBtn} testID="atendimento-calendario-mes-anterior">
          <Ionicons name="chevron-back" size={18} color={colors.brandPrimary} />
        </Pressable>
        <Text style={styles.mesTexto}>{MESES[mes]} de {ano}</Text>
        <Pressable onPress={() => trocarMes(1)} hitSlop={8} style={styles.navBtn} testID="atendimento-calendario-mes-proximo">
          <Ionicons name="chevron-forward" size={18} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <View style={styles.colHeaderRow}>
        {DIAS_COL.map((c, i) => (
          <Text key={i} style={styles.colHeaderText}>{c}</Text>
        ))}
      </View>

      {semanas.map((semana, wi) => (
        <View key={wi} style={styles.semanaRow}>
          {semana.map((d, di) => {
            if (!d) return <View key={di} style={styles.celula} />;
            const iso = toIso(d);
            const isHoje = iso === hoje;
            const isSel = iso === selecionado;
            return (
              <Pressable
                key={di}
                onPress={() => onSelecionarDia(iso)}
                style={[styles.celula, isSel && styles.celulaSel]}
                testID={`atendimento-calendario-dia-${iso}`}
              >
                <Text style={[styles.celulaText, isSel && styles.celulaTextSel, isHoje && !isSel && styles.celulaTextHoje]}>
                  {d.getDate()}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ))}

      <Pressable
        onPress={() => onSelecionarDia(hojeIso())}
        style={styles.hojeBtn}
        testID="atendimento-calendario-hoje"
      >
        <Text style={styles.hojeBtnText}>Hoje</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  navBtn: { padding: 4 },
  mesTexto: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  colHeaderRow: { flexDirection: "row" },
  colHeaderText: { flex: 1, textAlign: "center", fontSize: 11, color: colors.muted, fontWeight: "600", paddingVertical: 4 },
  semanaRow: { flexDirection: "row" },
  celula: { flex: 1, aspectRatio: 1, alignItems: "center", justifyContent: "center" },
  celulaSel: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill },
  celulaText: { fontSize: 13, color: colors.onSurface },
  celulaTextSel: { color: colors.onBrandPrimary, fontWeight: "700" },
  celulaTextHoje: { color: colors.brandPrimary, fontWeight: "700" },
  hojeBtn: { alignSelf: "center", marginTop: spacing.sm, paddingVertical: 6, paddingHorizontal: spacing.md },
  hojeBtnText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
});
