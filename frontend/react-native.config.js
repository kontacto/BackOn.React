// @ts-check
/**
 * TODO(windows): these community modules' Windows native implementations are built
 * against the old Paper/UWP architecture (Microsoft.ReactNative.Uwp, RnwNewArch=false)
 * and refuse to build against this app's New Architecture (Fabric + WinUI3/Composition
 * — required by the cpp-app template this project scaffolded with, RnwNewArch=true) —
 * hard MSBuild error, not fixable via project properties. Excluded from Windows
 * autolinking so the rest of the app builds; calls into these on Windows will throw
 * "NativeModule not found" until each is revisited (swap for a Fabric-compatible
 * alternative, or wait for the package to ship New Architecture Windows support).
 * - @react-native-async-storage/async-storage: credentials already go through
 *   expo-secure-store, not AsyncStorage (see src/services/SecureStorageService.ts)
 *   — lower-priority storage (connections list, session, ml filters) is affected.
 * - @react-native-community/datetimepicker: date/time picker UI on Windows will
 *   need a fallback (e.g. a custom modal) until this is resolved.
 * - react-native-screens: pulled in transitively by @react-navigation/native-stack
 *   and expo-router; without the native module, navigation falls back to plain-View
 *   screens (no native screen container optimization) instead of crashing, since
 *   react-navigation degrades gracefully when the native module isn't linked.
 * - react-native-webview: any screen embedding a WebView (e.g. NFe/boleto preview)
 *   will need a Windows-specific fallback (e.g. open in default browser) until this
 *   is resolved.
 */
module.exports = {
  dependencies: {
    "@react-native-async-storage/async-storage": {
      platforms: {
        windows: null,
      },
    },
    "@react-native-community/datetimepicker": {
      platforms: {
        windows: null,
      },
    },
    "react-native-screens": {
      platforms: {
        windows: null,
      },
    },
    "react-native-webview": {
      platforms: {
        windows: null,
      },
    },
  },
};
