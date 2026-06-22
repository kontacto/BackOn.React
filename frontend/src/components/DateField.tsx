import { useEffect, useMemo, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/theme/colors";

type Props = {
  label?: string;
  value: string | null; // ISO YYYY-MM-DD
  onChange: (iso: string | null) => void;
  placeholder?: string;
  testID?: string;
  allowClear?: boolean;
  minimumDate?: Date;
  maximumDate?: Date;
};

const MONTHS_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];
const WEEKDAYS_PT = ["D", "S", "T", "Q", "Q", "S", "S"];

function pad2(n: number) {
  return String(n).padStart(2, "0");
}
function isoToBR(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : "";
}
function dateToISO(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}
function parseISO(iso: string | null): Date | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map((s) => parseInt(s, 10));
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}
function stripTime(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export default function DateField({
  label,
  value,
  onChange,
  placeholder = "DD/MM/AAAA",
  testID,
  allowClear = true,
  minimumDate,
  maximumDate,
}: Props) {
  const [open, setOpen] = useState(false);
  const today = useMemo(() => stripTime(new Date()), []);

  // Mês exibido no calendário. Inicia em value (se houver) ou no mês atual.
  const initialView = useMemo(() => {
    const d = parseISO(value) || new Date();
    return { year: d.getFullYear(), month: d.getMonth() };
  }, [value]);
  const [viewYear, setViewYear] = useState(initialView.year);
  const [viewMonth, setViewMonth] = useState(initialView.month);
  const [yearPickerOpen, setYearPickerOpen] = useState(false);

  // Sempre que abrir, sincroniza com o value atual.
  useEffect(() => {
    if (open) {
      const d = parseISO(value) || new Date();
      setViewYear(d.getFullYear());
      setViewMonth(d.getMonth());
      setYearPickerOpen(false);
    }
  }, [open, value]);

  const minD = minimumDate ? stripTime(minimumDate) : null;
  const maxD = maximumDate ? stripTime(maximumDate) : null;

  function isDisabled(d: Date): boolean {
    if (minD && d < minD) return true;
    if (maxD && d > maxD) return true;
    return false;
  }

  // Matriz 6x7 (42 células) do mês exibido.
  const cells = useMemo(() => {
    const firstDay = new Date(viewYear, viewMonth, 1);
    const startWeekday = firstDay.getDay(); // 0=Dom
    const start = new Date(viewYear, viewMonth, 1 - startWeekday);
    const out: Date[] = [];
    for (let i = 0; i < 42; i++) {
      out.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
    }
    return out;
  }, [viewYear, viewMonth]);

  const selectedDate = parseISO(value);

  function goPrevMonth() {
    if (viewMonth === 0) {
      setViewYear(viewYear - 1);
      setViewMonth(11);
    } else {
      setViewMonth(viewMonth - 1);
    }
  }
  function goNextMonth() {
    if (viewMonth === 11) {
      setViewYear(viewYear + 1);
      setViewMonth(0);
    } else {
      setViewMonth(viewMonth + 1);
    }
  }

  function handlePick(d: Date) {
    if (isDisabled(d)) return;
    onChange(dateToISO(d));
    setOpen(false);
  }

  function handleToday() {
    if (isDisabled(today)) return;
    onChange(dateToISO(today));
    setOpen(false);
  }

  // Atalhos rápidos (Amanhã / +7 dias / Fim do mês)
  const shortcuts = useMemo(() => {
    const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
    const plus7 = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 7);
    const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return [
      { key: "tomorrow", label: "Amanhã", date: tomorrow },
      { key: "plus7", label: "+7 dias", date: plus7 },
      { key: "eom", label: "Fim do mês", date: endOfMonth },
    ];
  }, [today]);

  function handleShortcut(d: Date) {
    if (isDisabled(d)) return;
    onChange(dateToISO(d));
    setOpen(false);
  }

  // Lista de anos para o picker (centrado no atual, ±60 anos, respeitando limites).
  const yearRange = useMemo(() => {
    const base = viewYear;
    const minY = minD ? minD.getFullYear() : base - 60;
    const maxY = maxD ? maxD.getFullYear() : base + 60;
    const out: number[] = [];
    for (let y = minY; y <= maxY; y++) out.push(y);
    return out;
  }, [viewYear, minD, maxD]);

  return (
    <View style={{ flex: 1 }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View style={styles.row}>
        <Pressable
          onPress={() => setOpen(true)}
          style={({ pressed }) => [styles.box, pressed && { opacity: 0.75 }]}
          testID={testID}
        >
          <Ionicons name="calendar-outline" size={16} color={colors.muted} />
          <Text style={[styles.text, !value && { color: colors.muted }]}>
            {value ? isoToBR(value) : placeholder}
          </Text>
        </Pressable>
        {allowClear && value ? (
          <Pressable
            onPress={() => onChange(null)}
            hitSlop={8}
            style={({ pressed }) => [styles.clearBtn, pressed && { opacity: 0.7 }]}
            testID={testID ? `${testID}-clear` : undefined}
          >
            <Ionicons name="close-circle" size={20} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setOpen(false)}>
          <Pressable
            style={styles.modalCard}
            onPress={(e) => e.stopPropagation()}
            testID={testID ? `${testID}-modal` : undefined}
          >
            {/* Cabeçalho com mês/ano e navegação */}
            <View style={styles.calHeader}>
              <Pressable
                onPress={goPrevMonth}
                hitSlop={8}
                style={({ pressed }) => [styles.navBtn, pressed && { opacity: 0.6 }]}
                testID={testID ? `${testID}-prev` : undefined}
              >
                <Ionicons name="chevron-back" size={22} color={colors.brandPrimary} />
              </Pressable>

              <Pressable
                onPress={() => setYearPickerOpen((v) => !v)}
                style={({ pressed }) => [styles.titleBtn, pressed && { opacity: 0.75 }]}
                testID={testID ? `${testID}-title` : undefined}
              >
                <Text style={styles.titleText}>
                  {MONTHS_PT[viewMonth]} {viewYear}
                </Text>
                <Ionicons
                  name={yearPickerOpen ? "chevron-up" : "chevron-down"}
                  size={16}
                  color={colors.brandPrimary}
                />
              </Pressable>

              <Pressable
                onPress={goNextMonth}
                hitSlop={8}
                style={({ pressed }) => [styles.navBtn, pressed && { opacity: 0.6 }]}
                testID={testID ? `${testID}-next` : undefined}
              >
                <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
              </Pressable>
            </View>

            {yearPickerOpen ? (
              <ScrollView
                style={styles.yearList}
                contentContainerStyle={styles.yearListContent}
                testID={testID ? `${testID}-year-list` : undefined}
              >
                {yearRange.map((y) => {
                  const sel = y === viewYear;
                  return (
                    <Pressable
                      key={y}
                      onPress={() => {
                        setViewYear(y);
                        setYearPickerOpen(false);
                      }}
                      style={({ pressed }) => [
                        styles.yearCell,
                        sel && styles.yearCellSel,
                        pressed && { opacity: 0.7 },
                      ]}
                      testID={testID ? `${testID}-year-${y}` : undefined}
                    >
                      <Text style={[styles.yearText, sel && styles.yearTextSel]}>{y}</Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            ) : (
              <>
                {/* Dias da semana */}
                <View style={styles.weekRow}>
                  {WEEKDAYS_PT.map((w, i) => (
                    <View key={i} style={styles.weekCell}>
                      <Text style={styles.weekText}>{w}</Text>
                    </View>
                  ))}
                </View>

                {/* Grid 6x7 */}
                <View style={styles.grid}>
                  {cells.map((d, i) => {
                    const inMonth = d.getMonth() === viewMonth;
                    const isToday = d.getTime() === today.getTime();
                    const isSel =
                      !!selectedDate &&
                      d.getFullYear() === selectedDate.getFullYear() &&
                      d.getMonth() === selectedDate.getMonth() &&
                      d.getDate() === selectedDate.getDate();
                    const disabled = isDisabled(d);
                    return (
                      <Pressable
                        key={i}
                        onPress={() => handlePick(d)}
                        disabled={disabled}
                        style={({ pressed }) => [
                          styles.dayCell,
                          isSel && styles.dayCellSel,
                          !isSel && isToday && styles.dayCellToday,
                          pressed && !disabled && !isSel && { backgroundColor: colors.brandTertiary },
                        ]}
                        testID={testID ? `${testID}-day-${dateToISO(d)}` : undefined}
                      >
                        <Text
                          style={[
                            styles.dayText,
                            !inMonth && styles.dayTextOut,
                            isSel && styles.dayTextSel,
                            !isSel && isToday && styles.dayTextToday,
                            disabled && styles.dayTextDisabled,
                          ]}
                        >
                          {d.getDate()}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </>
            )}

            {/* Atalhos rápidos */}
            {!yearPickerOpen ? (
              <View style={styles.shortcutsRow}>
                {shortcuts.map((s) => {
                  const disabled = isDisabled(s.date);
                  return (
                    <Pressable
                      key={s.key}
                      onPress={() => handleShortcut(s.date)}
                      disabled={disabled}
                      style={({ pressed }) => [
                        styles.shortcutChip,
                        pressed && !disabled && { opacity: 0.7 },
                        disabled && { opacity: 0.35 },
                      ]}
                      testID={testID ? `${testID}-shortcut-${s.key}` : undefined}
                    >
                      <Text style={styles.shortcutText}>{s.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}

            {/* Rodapé com ações */}
            <View style={styles.footer}>
              {allowClear && value ? (
                <Pressable
                  onPress={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                  style={({ pressed }) => [styles.footerBtn, pressed && { opacity: 0.65 }]}
                  testID={testID ? `${testID}-clear-action` : undefined}
                >
                  <Text style={styles.footerBtnText}>Limpar</Text>
                </Pressable>
              ) : (
                <View style={{ flex: 1 }} />
              )}
              <Pressable
                onPress={handleToday}
                disabled={isDisabled(today)}
                style={({ pressed }) => [
                  styles.footerBtn,
                  pressed && { opacity: 0.65 },
                  isDisabled(today) && { opacity: 0.35 },
                ]}
                testID={testID ? `${testID}-today` : undefined}
              >
                <Text style={styles.footerBtnText}>Hoje</Text>
              </Pressable>
              <Pressable
                onPress={() => setOpen(false)}
                style={({ pressed }) => [styles.footerBtn, pressed && { opacity: 0.65 }]}
                testID={testID ? `${testID}-cancel` : undefined}
              >
                <Text style={styles.footerBtnText}>Cancelar</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const CELL_SIZE = 38;

const styles = StyleSheet.create({
  label: {
    fontSize: 12,
    color: colors.muted,
    marginBottom: 4,
    fontWeight: "500",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 4 },
  box: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 42,
  },
  text: { fontSize: 14, color: colors.onSurface },
  clearBtn: { padding: 4 },

  // Modal
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  modalCard: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
    shadowColor: "#000",
    shadowOpacity: 0.25,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 12,
  },

  // Cabeçalho calendário
  calHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  navBtn: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.pill,
  },
  titleBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.sm,
  },
  titleText: {
    fontSize: 16,
    fontWeight: "600",
    color: colors.brandPrimary,
    textTransform: "capitalize",
  },

  // Year picker
  yearList: { maxHeight: 280, marginBottom: spacing.sm },
  yearListContent: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: 6,
  },
  yearCell: {
    minWidth: 72,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: radius.sm,
    alignItems: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  yearCellSel: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  yearText: { fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  yearTextSel: { color: colors.onBrandPrimary, fontWeight: "700" },

  // Semana
  weekRow: { flexDirection: "row" },
  weekCell: {
    width: CELL_SIZE,
    height: 28,
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
  },
  weekText: {
    fontSize: 11,
    color: colors.muted,
    fontWeight: "600",
    textTransform: "uppercase",
  },

  // Grid
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
  },
  dayCell: {
    width: `${100 / 7}%`,
    height: CELL_SIZE,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.pill,
    marginVertical: 2,
  },
  dayCellSel: {
    backgroundColor: colors.brandPrimary,
  },
  dayCellToday: {
    borderWidth: 1,
    borderColor: colors.brandPrimary,
  },
  dayText: { fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  dayTextOut: { color: colors.muted, opacity: 0.45 },
  dayTextSel: { color: colors.onBrandPrimary, fontWeight: "700" },
  dayTextToday: { color: colors.brandPrimary, fontWeight: "700" },
  dayTextDisabled: { color: colors.muted, opacity: 0.3 },

  // Rodapé
  shortcutsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    paddingTop: spacing.sm,
  },
  shortcutChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    borderWidth: 1,
    borderColor: colors.brandTertiary,
  },
  shortcutText: {
    fontSize: 12,
    color: colors.brandPrimary,
    fontWeight: "600",
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 4,
    paddingTop: spacing.sm,
    marginTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  footerBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.sm,
  },
  footerBtnText: {
    fontSize: 13,
    color: colors.brandPrimary,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
});
