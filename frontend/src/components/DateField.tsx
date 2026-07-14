import { useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import DateTimePicker, { DateTimePickerEvent } from "@react-native-community/datetimepicker";
import { Ionicons } from "@/src/components/Ionicons";
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

function isoToBR(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : "";
}

function dateToISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseISO(iso: string | null): Date {
  if (!iso) return new Date();
  const [y, m, d] = iso.split("-").map((s) => parseInt(s, 10));
  if (!y || !m || !d) return new Date();
  return new Date(y, m - 1, d);
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

  // `@react-native-community/datetimepicker` não tem implementação para web (retorna
  // null e só emite um warning) — por isso usamos um <input type="date"> nativo do
  // navegador aqui, em vez do fluxo de abrir modal/spinner usado no mobile.
  if (Platform.OS === "web") {
    return (
      <View style={{ flex: 1 }}>
        {label ? <Text style={styles.label}>{label}</Text> : null}
        <View style={styles.row}>
          <View style={styles.box} testID={testID}>
            <Ionicons name="calendar-outline" size={16} color={colors.muted} />
            {/* eslint-disable-next-line react/no-unknown-property -- input HTML nativo (build web) */}
            <input
              type="date"
              value={value || ""}
              onChange={(e) => onChange(e.target.value || null)}
              min={minimumDate ? dateToISO(minimumDate) : undefined}
              max={maximumDate ? dateToISO(maximumDate) : undefined}
              style={{
                flex: 1,
                marginLeft: 8,
                border: "none",
                outline: "none",
                background: "transparent",
                fontSize: 14,
                color: colors.onSurface,
                fontFamily: "inherit",
              }}
            />
          </View>
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
      </View>
    );
  }

  const handleChange = (event: DateTimePickerEvent, selected?: Date) => {
    // Android fires once and we close. iOS keeps open (spinner) until OK pressed.
    if (Platform.OS === "android") {
      setOpen(false);
      if (event.type === "set" && selected) {
        onChange(dateToISO(selected));
      }
      return;
    }
    if (selected) onChange(dateToISO(selected));
  };

  return (
    <View style={{ flex: 1 }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View style={styles.row}>
        <Pressable
          onPress={() => setOpen(true)}
          style={({ pressed }) => [styles.box, pressed && { opacity: 0.7 }]}
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

      {open && Platform.OS === "ios" ? (
        <View style={styles.iosWrap}>
          <DateTimePicker
            value={parseISO(value)}
            mode="date"
            display="spinner"
            onChange={handleChange}
            minimumDate={minimumDate}
            maximumDate={maximumDate}
            locale="pt-BR"
          />
          <View style={styles.iosBtnRow}>
            <Pressable onPress={() => setOpen(false)} style={styles.iosBtn}>
              <Text style={styles.iosBtnText}>OK</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {open && Platform.OS === "android" ? (
        <DateTimePicker
          value={parseISO(value)}
          mode="date"
          display="default"
          onChange={handleChange}
          minimumDate={minimumDate}
          maximumDate={maximumDate}
        />
      ) : null}

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
  iosWrap: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.sm,
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iosBtnRow: { flexDirection: "row", justifyContent: "flex-end", marginTop: spacing.sm },
  iosBtn: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  iosBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
});
