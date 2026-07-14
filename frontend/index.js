// Entry point shim for native builds that resolve a bare "./index" bundle
// (react-native-windows' App.cpp requests "index" regardless of the
// "main": "expo-router/entry" field in package.json). Web/Android/iOS use
// "main" directly via Expo tooling and never touch this file.
//
// The Windows globalThis.expo polyfill (windows-polyfills/setUpExpoGlobal.js)
// is NOT required here — it runs earlier, injected as a Metro "preModule" in
// metro.config.js, because @expo/metro-runtime's own preModule already needs
// globalThis.expo before this file's first line ever executes.

// react-native-screens' native module is excluded on Windows (see
// react-native.config.js). expo-router's own <Stack> (@react-navigation/
// native-stack) has no fallback for that -- it renders react-native-screens'
// native view managers unconditionally, "Unimplemented component" and all
// (confirmed in NativeStackView.native.tsx, no enableScreens escape hatch).
// That's why app/_layout.tsx swaps in a classic @react-navigation/stack
// navigator (src/navigation/WindowsStack.tsx) for Windows specifically --
// it renders its header in plain JS and only *optionally* uses
// react-native-screens' Screen/ScreenContainer, checking `screensEnabled()`
// per render and falling back to a plain <View> when it's false
// (react-native-screens/src/components/Screen.tsx, ScreenContainer.tsx).
// Must run before expo-router mounts any navigator, hence here rather than
// inside a component.
const { Platform } = require("react-native");
if (Platform.OS === "windows") {
  const { enableScreens } = require("react-native-screens");
  enableScreens(false);
}

require("expo-router/entry");
