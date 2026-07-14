import { createStackNavigator } from "@react-navigation/stack";
import { withLayoutContext } from "expo-router";

// expo-router's own <Stack> is hardcoded to @react-navigation/native-stack
// (node_modules/expo-router/build/layouts/StackClient.js), which renders its
// header/screen container via react-native-screens' native view managers
// unconditionally -- no JS fallback. That native module isn't linked on
// Windows (react-native.config.js), so it shows as a red "Unimplemented
// component" placeholder there.
//
// The classic @react-navigation/stack navigator, wired up the same way
// (withLayoutContext is expo-router's public API for swapping the
// navigator implementation), renders its header in plain JS and only
// *optionally* uses react-native-screens' Screen/ScreenContainer --
// react-native-screens/src/components/Screen.tsx and ScreenContainer.tsx
// both check `screensEnabled()` per render and fall back to a plain <View>
// when it's false. index.js calls enableScreens(false) on Windows so that
// fallback kicks in here, avoiding the placeholder entirely.
const { Navigator } = createStackNavigator();
export const WindowsStack = withLayoutContext(Navigator);
