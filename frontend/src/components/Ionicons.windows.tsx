import { Text, type TextProps } from "react-native";
import glyphMap from "@expo/vector-icons/build/vendor/react-native-vector-icons/glyphmaps/Ionicons.json";

// expo-font's native module isn't ported to Windows (windows-polyfills/
// setUpExpoGlobal.js no-ops it instead of crashing), so @expo/vector-icons'
// <Ionicons> never actually loads the font and renders glyphs via a bare
// "ionicons" fontFamily that Windows has no way to resolve — shows as tofu
// boxes. RNW also has no font-family alias API to give a packaged font a
// short lookup name (the "SetFontFamilyPaths" feature request has been open
// since 2019: https://github.com/microsoft/react-native-windows/issues/3816),
// so the only working way to reference our packaged Ionicons.ttf
// (windows/frontend.Package/Assets/Fonts/Ionicons.ttf) is the standard WinUI
// "path#FontName" syntax as the literal fontFamily value — this renders the
// glyph directly from the same glyph map @expo/vector-icons uses, instead of
// going through its font-loading machinery. No leading "/" on the path: WinUI3
// (unlike classic UWP) fails to resolve it with one.
type Props = {
  name: keyof typeof glyphMap;
  size?: number;
  color?: string;
  style?: TextProps["style"];
};

function Ionicons({ name, size = 12, color = "#000", style, ...rest }: Props & Record<string, unknown>) {
  const codepoint = glyphMap[name];
  if (codepoint == null) return null;
  return (
    <Text
      style={[{ fontFamily: "Assets/Fonts/Ionicons.ttf#Ionicons", fontSize: size, color }, style]}
      {...rest}
    >
      {String.fromCodePoint(codepoint)}
    </Text>
  );
}

Ionicons.glyphMap = glyphMap;

export { Ionicons };
