import { useMemo, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/theme/colors";

export type SelectOption = {
  value: string | number;
  label: string;
  sub?: string;
};

type Props = {
  label?: string;
  value: string | number | null;
  onChange: (value: string | number | null) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  searchable?: boolean;
  testID?: string;
  modalTitle?: string;
  allowClear?: boolean;
};

export default function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder = "Selecione…",
  disabled,
  searchable = true,
  testID,
  modalTitle,
  allowClear = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");

  const selected = useMemo(
    () => options.find((o) => String(o.value) === String(value)) || null,
    [options, value]
  );

  const filtered = useMemo(() => {
    if (!term.trim()) return options;
    const t = term.toLowerCase();
    return options.filter(
      (o) => o.label.toLowerCase().includes(t) || (o.sub || "").toLowerCase().includes(t)
    );
  }, [options, term]);

  return (
    <View style={{ flex: 1 }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <Pressable
        onPress={() => {
          if (!disabled) {
            setTerm("");
            setOpen(true);
          }
        }}
        style={({ pressed }) => [
          styles.box,
          disabled && styles.boxDisabled,
          pressed && !disabled && { opacity: 0.75 },
        ]}
        testID={testID}
      >
        <View style={{ flex: 1 }}>
          {selected ? (
            <>
              <Text style={[styles.text, disabled && { color: colors.muted }]} numberOfLines={1}>
                {selected.label}
              </Text>
              {selected.sub ? (
                <Text style={styles.sub} numberOfLines={1}>{selected.sub}</Text>
              ) : null}
            </>
          ) : (
            <Text style={[styles.text, { color: colors.muted }]} numberOfLines={1}>
              {placeholder}
            </Text>
          )}
        </View>
        {allowClear && selected && !disabled ? (
          <Pressable
            onPress={(e) => {
              e.stopPropagation();
              onChange(null);
            }}
            hitSlop={6}
            style={({ pressed }) => [styles.clearBtn, pressed && { opacity: 0.7 }]}
            testID={testID ? `${testID}-clear` : undefined}
          >
            <Ionicons name="close-circle" size={18} color={colors.muted} />
          </Pressable>
        ) : null}
        <Ionicons
          name={disabled ? "lock-closed-outline" : "chevron-down"}
          size={16}
          color={disabled ? colors.muted : colors.muted}
        />
      </Pressable>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{modalTitle || label || "Selecione"}</Text>
              <Pressable onPress={() => setOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>

            {searchable ? (
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={term}
                  onChangeText={setTerm}
                  placeholder="Buscar…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  autoFocus={false}
                />
              </View>
            ) : null}

            <ScrollView style={{ maxHeight: 420 }} keyboardShouldPersistTaps="handled">
              {allowClear && !term.trim() ? (
                <Pressable
                  onPress={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                  style={({ pressed }) => [styles.optRow, !selected && styles.optRowSel, pressed && { opacity: 0.7 }]}
                  testID={testID ? `${testID}-opt-all` : undefined}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.optLabel, !selected && { color: colors.brandPrimary, fontWeight: "600" }]}>
                      {placeholder}
                    </Text>
                  </View>
                  {!selected ? <Ionicons name="checkmark" size={20} color={colors.brandPrimary} /> : null}
                </Pressable>
              ) : null}
              {filtered.length === 0 ? (
                <Text style={styles.empty}>Nenhuma opção.</Text>
              ) : (
                filtered.map((o) => {
                  const isSel = String(o.value) === String(value);
                  return (
                    <Pressable
                      key={String(o.value)}
                      onPress={() => {
                        onChange(o.value);
                        setOpen(false);
                      }}
                      style={({ pressed }) => [
                        styles.optRow,
                        isSel && styles.optRowSel,
                        pressed && { opacity: 0.7 },
                      ]}
                      testID={testID ? `${testID}-opt-${o.value}` : undefined}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.optLabel, isSel && { color: colors.brandPrimary, fontWeight: "600" }]} numberOfLines={1}>
                          {o.label}
                        </Text>
                        {o.sub ? <Text style={styles.optSub} numberOfLines={1}>{o.sub}</Text> : null}
                      </View>
                      {isSel ? <Ionicons name="checkmark" size={20} color={colors.brandPrimary} /> : null}
                    </Pressable>
                  );
                })
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    fontSize: 12,
    color: colors.muted,
    marginBottom: 4,
    fontWeight: "500",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  box: {
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
  boxDisabled: { opacity: 0.65, backgroundColor: colors.surface },
  text: { fontSize: 14, color: colors.onSurface },
  sub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  clearBtn: { padding: 2 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
    minHeight: 460,
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  optRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  optRowSel: { backgroundColor: colors.brandTertiary },
  optLabel: { fontSize: 14, color: colors.onSurface },
  optSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, padding: spacing.lg, fontSize: 13 },
});
