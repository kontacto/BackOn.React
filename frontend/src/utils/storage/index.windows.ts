// Windows storage (Metro prefers this over index.ts on the "windows" platform).
// Helpers never throw: reads return `fallback`, writes return `false`.
// Values supported: string | number | boolean | null (JSON-serialized on disk).
// Usage: import { storage } from "@/src/utils/storage"; await storage.getItem(key, fallback);
//
// @react-native-async-storage/async-storage has no Windows native module (see
// react-native.config.js — excluded from Windows autolinking, its Windows
// port doesn't support the New Architecture this app uses) and, unlike most
// gaps on this platform, it doesn't fail gracefully: importing the package at
// all throws synchronously ("NativeModule: AsyncStorage is null"), before any
// try/catch around individual calls gets a chance to run. So general KV here
// is in-memory only — cleared when the app closes. secure* still goes through
// expo-secure-store like the native implementation: it has no Windows native
// module either, but expo-modules-core packages degrade gracefully (thanks to
// windows-polyfills/setUpExpoGlobal.js) instead of throwing at import time, so
// it's safe to keep using the same code path as index.ts for those three.

import * as SecureStore from "expo-secure-store";

import AsyncStorage from "./asyncStorageCompat";
import { AssertNoExtras, StorageBase, StorageItemValue } from "./storage-base";

export class Storage extends StorageBase {
  async getItem<Fallback extends StorageItemValue>(
    key: string,
    fallback: Fallback,
  ): Promise<Fallback | null> {
    const raw = await AsyncStorage.getItem(key);
    return this.retrieve(raw, fallback);
  }

  async setItem<Value extends StorageItemValue>(
    key: string,
    value: Value,
  ): Promise<boolean> {
    try {
      await AsyncStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      this.warn("setItem", key, e);
      return false;
    }
  }

  async removeItem(key: string): Promise<boolean> {
    await AsyncStorage.removeItem(key);
    return true;
  }

  // Sensitive values — same expo-secure-store path as native; degrades to a
  // silent no-op on Windows (see windows-polyfills/setUpExpoGlobal.js) rather
  // than throwing, so no special-casing needed here.
  async secureGet<Fallback extends StorageItemValue>(
    key: string,
    fallback: Fallback,
  ): Promise<Fallback | null> {
    try {
      const raw = await SecureStore.getItemAsync(key);
      return this.retrieve(raw, fallback);
    } catch (e) {
      this.warn("secureGet", key, e);
      return fallback;
    }
  }

  async secureSet<Value extends StorageItemValue>(
    key: string,
    value: Value,
  ): Promise<boolean> {
    try {
      await SecureStore.setItemAsync(key, JSON.stringify(value));
      return true;
    } catch (e) {
      this.warn("secureSet", key, e);
      return false;
    }
  }

  async secureRemove(key: string): Promise<boolean> {
    try {
      await SecureStore.deleteItemAsync(key);
      return true;
    } catch (e) {
      this.warn("secureRemove", key, e);
      return false;
    }
  }
}

export const storage = new Storage();

// Compile-time guard: any new method must be declared in storage-base.ts first.
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- intentional compile-time-only assertion
type _NoExtras = AssertNoExtras<Exclude<keyof Storage, keyof StorageBase>>;
