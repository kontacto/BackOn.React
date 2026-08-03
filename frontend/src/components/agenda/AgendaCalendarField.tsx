// Campo de Data com calendário PRÓPRIO (não o nativo do navegador) — os
// dias em que o profissional NÃO atende ficam de fato desabilitados
// (cinza, sem clique), não só rejeitados depois de escolhidos. Motivo de
// existir separado de `WebDateField` (o padrão global do projeto): o
// `<input type="date">` nativo não permite desabilitar dias da semana
// específicos — nenhum navegador expõe esse controle pra JS. User-directed
// 2026-07-28: "quero um calendar fixo com as datas que o profissional não
// trabalha, fique enable false desabilitada. não permitir nem
// selecionar. tanto na agenda, quanto na tela de atendimento" — usado em
// `app/agenda.tsx`, `pedido/AgendarModal.tsx` e
// `agenda/AtendimentoAvulsoModal.tsx`.
//
// `diasAtende` (Set de `Date.getDay()`, 0=Domingo) vem do hook
// `useDiasAtende` — `null` = ainda não sabe (nenhum profissional
// escolhido ainda), campo fica desabilitado inteiro nesse caso.
import { useEffect, useRef, useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors, radius, spacing } from "@/src/theme/colors";

const isWeb = Platform.OS === "web";

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
  value: string | null;
  onChange: (v: string) => void;
  // Dias da semana habilitados (0=Domingo..6=Sábado). `null` = ainda não
  // sabe (campo fica desabilitado); conjunto vazio = profissional sem
  // nenhum dia configurado (campo abre mas todo dia fica desabilitado,
  // com aviso).
  diasAtende: Set<number> | null;
  testID?: string;
  disabled?: boolean;
};

export default function AgendaCalendarField({ value, onChange, diasAtende, testID, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState(() => fromIso(value || hojeIso()));
  const wrapRef = useRef<View>(null);

  useEffect(() => {
    if (value) setAnchor(fromIso(value));
  }, [value]);

  if (!isWeb) return null;

  const efetivamenteDesabilitado = disabled || !diasAtende;

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
  const selecionado = value || null;

  const pickDia = (d: Date) => {
    onChange(toIso(d));
    setOpen(false);
  };

  const trocarMes = (delta: number) => setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + delta, 1));

  return (
    <View ref={wrapRef} style={{ position: "relative", zIndex: open ? 1000 : 1 }}>
      <Pressable
        onPress={() => !efetivamenteDesabilitado && setOpen((v) => !v)}
        disabled={efetivamenteDesabilitado}
        style={[styles.wrap, efetivamenteDesabilitado && styles.wrapDisabled, open && styles.wrapFocused]}
        testID={testID}
      >
        <Ionicons name="calendar-outline" size={16} color={colors.muted} />
        <Text style={[styles.valueText, !value && styles.placeholderText]}>
          {value ? `${value.slice(8, 10)}/${value.slice(5, 7)}/${value.slice(0, 4)}` : "dd/mm/aaaa"}
        </Text>
      </Pressable>

      {open ? (
        <>
          <Pressable style={styles.backdrop} onPress={() => setOpen(false)} />
          <View style={styles.popup}>
            <View style={styles.popupHeader}>
              <Text style={styles.popupMes}>{MESES[mes]} de {ano}</Text>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Pressable onPress={() => trocarMes(-1)} hitSlop={8} testID="agenda-calendar-mes-anterior">
                  <Ionicons name="chevron-up" size={16} color={colors.brandPrimary} />
                </Pressable>
                <Pressable onPress={() => trocarMes(1)} hitSlop={8} testID="agenda-calendar-mes-proximo">
                  <Ionicons name="chevron-down" size={16} color={colors.brandPrimary} />
                </Pressable>
              </View>
            </View>

            <View style={styles.colHeaderRow}>
              {DIAS_COL.map((c, i) => (
                <Text key={i} style={styles.colHeaderText}>{c}</Text>
              ))}
            </View>

            <ScrollView style={{ maxHeight: 220 }}>
              {semanas.map((semana, wi) => (
                <View key={wi} style={styles.semanaRow}>
                  {semana.map((d, di) => {
                    if (!d) return <View key={di} style={styles.celula} />;
                    const iso = toIso(d);
                    const habilitado = diasAtende ? diasAtende.has(d.getDay()) : false;
                    const isHoje = iso === hoje;
                    const isSel = iso === selecionado;
                    return (
                      <Pressable
                        key={di}
                        onPress={() => habilitado && pickDia(d)}
                        disabled={!habilitado}
                        style={[
                          styles.celula,
                          isSel && styles.celulaSel,
                          !habilitado && styles.celulaDesabilitada,
                        ]}
                        testID={`agenda-calendar-dia-${iso}`}
                      >
                        <Text
                          style={[
                            styles.celulaText,
                            !habilitado && styles.celulaTextDesabilitada,
                            isSel && styles.celulaTextSel,
                            isHoje && !isSel && styles.celulaTextHoje,
                          ]}
                        >
                          {d.getDate()}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ))}
            </ScrollView>

            <View style={styles.popupFooter}>
              <Pressable onPress={() => { onChange(""); setOpen(false); }} testID="agenda-calendar-limpar">
                <Text style={styles.footerLink}>Limpar</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  const d = new Date();
                  if (diasAtende && diasAtende.has(d.getDay())) pickDia(d);
                  else setAnchor(new Date(d.getFullYear(), d.getMonth(), 1));
                }}
                testID="agenda-calendar-hoje"
              >
                <Text style={styles.footerLink}>Hoje</Text>
              </Pressable>
            </View>
            {diasAtende && diasAtende.size === 0 ? (
              <Text style={styles.avisoSemDias}>Nenhum dia de atendimento configurado para este profissional.</Text>
            ) : null}
          </View>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row", alignItems: "center", gap: 8, minHeight: 42,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, paddingVertical: 10, paddingHorizontal: 10,
  },
  wrapFocused: { borderColor: colors.brandPrimary, borderWidth: 1.5 },
  wrapDisabled: { opacity: 0.6 },
  valueText: { fontSize: 14, color: colors.onSurface },
  placeholderText: { color: colors.muted },
  backdrop: {
    position: "absolute", top: -1000, left: -1000, right: -1000, bottom: -1000,
  },
  popup: {
    position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 1000,
    width: 260, backgroundColor: colors.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.sm,
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  popupHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.xs, paddingHorizontal: 4 },
  popupMes: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  colHeaderRow: { flexDirection: "row" },
  colHeaderText: { flex: 1, textAlign: "center", fontSize: 11, color: colors.muted, fontWeight: "600", paddingVertical: 4 },
  semanaRow: { flexDirection: "row" },
  celula: { flex: 1, aspectRatio: 1, alignItems: "center", justifyContent: "center" },
  celulaSel: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill },
  celulaDesabilitada: {},
  celulaText: { fontSize: 12, color: colors.onSurface },
  celulaTextDesabilitada: { color: colors.border },
  celulaTextSel: { color: colors.onBrandPrimary, fontWeight: "700" },
  celulaTextHoje: { color: colors.brandPrimary, fontWeight: "700" },
  popupFooter: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.xs, paddingHorizontal: 4 },
  footerLink: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  avisoSemDias: { fontSize: 11, color: colors.error, marginTop: spacing.xs, paddingHorizontal: 4 },
});
