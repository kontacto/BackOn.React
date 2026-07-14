// Re-exports the real AsyncStorage on every platform except Windows, which
// gets asyncStorageCompat.windows.ts instead (Metro picks by platform
// extension). Only exists so connections.ts/mlFilters.ts/session.ts — which
// use AsyncStorage.getItem/setItem/removeItem directly, bypassing the
// `storage` wrapper in index.ts/index.windows.ts — don't each need their own
// platform branching. See index.windows.ts for why Windows needs this at all
// (importing @react-native-async-storage/async-storage at all throws
// synchronously there; there's no native module for this platform).
export { default } from "@react-native-async-storage/async-storage";
