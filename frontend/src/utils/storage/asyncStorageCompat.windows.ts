// Windows has no @react-native-async-storage/async-storage native module
// (excluded in react-native.config.js) and importing the real package throws
// synchronously ("NativeModule: AsyncStorage is null") — see
// index.windows.ts for the full explanation. Backed by a small custom native
// module (windows/frontend/LocalStorageModule.h/.cpp, registered via
// AddAttributedModules in frontend.cpp) that persists to plain text files
// under the app's LocalFolder — RNW ships no built-in persistent-storage API
// of its own. Only implements the 3 methods connections.ts/mlFilters.ts/
// session.ts actually use.
import { NativeModules } from "react-native";

const { WindowsLocalStorage } = NativeModules;

const AsyncStorageCompat = {
  async getItem(key: string): Promise<string | null> {
    const value: string | null | undefined = await WindowsLocalStorage.getItem(key);
    return value ?? null;
  },
  async setItem(key: string, value: string): Promise<void> {
    await WindowsLocalStorage.setItem(key, value);
  },
  async removeItem(key: string): Promise<void> {
    await WindowsLocalStorage.removeItem(key);
  },
};

export default AsyncStorageCompat;
