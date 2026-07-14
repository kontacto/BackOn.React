// Campo de data padronizado para telas web — substitui o antigo padrão de
// `<input type="date">` cru + `webDateInputStyle` duplicado em cada tela
// (Telemarketing, Cliente Completo, Contatos, Equipamentos, Entrada/Saída
// de Caixa, Notas Fiscais...). O `<input>` nativo continua sendo quem
// abre o seletor de data do navegador (mantém acessibilidade/atalhos de
// teclado nativos), mas ele próprio fica sem borda/fundo — quem desenha a
// caixa (borda, raio, cor, estado de foco) é o `View` por fora, igual a
// `TextInput`/`SelectField`. Ver "Padrão de Campo de Data (Web)" no
// CLAUDE.md.
import { useEffect, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { colors, radius } from "@/src/theme/colors";

let cssInjetado = false;
function injetarCssDoCampoData() {
  if (cssInjetado || typeof document === "undefined") return;
  cssInjetado = true;
  const style = document.createElement("style");
  style.id = "kontacto-web-date-field-css";
  style.textContent = `
    input.kontacto-date-input { cursor: pointer; }
    input.kontacto-date-input::-webkit-inner-spin-button,
    input.kontacto-date-input::-webkit-clear-button { display: none; }
    input.kontacto-date-input::-webkit-calendar-picker-indicator {
      cursor: pointer; opacity: 0.55; transition: opacity 0.15s ease;
    }
    input.kontacto-date-input::-webkit-calendar-picker-indicator:hover { opacity: 1; }
  `;
  document.head.appendChild(style);
}

type Props = {
  value: string | null | undefined; // ISO yyyy-mm-dd (ou HH:mm quando type="time")
  onChange: (v: string) => void;
  type?: "date" | "time";
  disabled?: boolean;
  testID?: string;
  min?: string;
  max?: string;
};

export default function WebDateField({ value, onChange, type = "date", disabled, testID, min, max }: Props) {
  const [focused, setFocused] = useState(false);

  useEffect(() => { injetarCssDoCampoData(); }, []);

  if (Platform.OS !== "web") return null;

  return (
    <View style={[styles.wrap, focused && styles.wrapFocused, disabled && styles.wrapDisabled]}>
      {/* eslint-disable-next-line react/no-unknown-property -- input HTML nativo (build web) */}
      <input
        type={type}
        className="kontacto-date-input"
        value={value || ""}
        onChange={(e: any) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={disabled}
        min={min}
        max={max}
        data-testid={testID}
        style={nativeStyle}
      />
    </View>
  );
}

const nativeStyle: any = {
  border: "none", outline: "none", background: "transparent", width: "100%",
  fontFamily: "inherit", fontSize: 14, color: colors.onSurface, boxSizing: "border-box", padding: 0,
};

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, paddingVertical: 10, paddingHorizontal: 10,
  },
  wrapFocused: { borderColor: colors.brandPrimary, borderWidth: 1.5 },
  wrapDisabled: { opacity: 0.6 },
});
