// Armazenamento seguro de credenciais (Keychain iOS / Keystore Android) via expo-secure-store.
// NUNCA usa AsyncStorage/LocalStorage para senha.
import * as SecureStore from "expo-secure-store";

import { AuthCredentials, ISecureStorageService } from "./types";
import { devLog } from "./logger";

const PREFIX = "biocred_";

function keyFor(connId: string): string {
  // SecureStore aceita apenas [A-Za-z0-9._-]; normaliza o connId.
  const safe = connId.replace(/[^A-Za-z0-9._-]/g, "_");
  return `${PREFIX}${safe}`;
}

class SecureStorageService implements ISecureStorageService {
  async saveCredentials(connId: string, creds: AuthCredentials): Promise<void> {
    try {
      await SecureStore.setItemAsync(keyFor(connId), JSON.stringify(creds), {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
    } catch (e) {
      devLog("SecureStorage.save error", e);
      throw e;
    }
  }

  async getCredentials(connId: string): Promise<AuthCredentials | null> {
    try {
      const raw = await SecureStore.getItemAsync(keyFor(connId));
      if (!raw) return null;
      const parsed = JSON.parse(raw) as AuthCredentials;
      if (!parsed?.usuario || !parsed?.senha) return null;
      return parsed;
    } catch (e) {
      devLog("SecureStorage.get error", e);
      return null;
    }
  }

  async deleteCredentials(connId: string): Promise<void> {
    try {
      await SecureStore.deleteItemAsync(keyFor(connId));
    } catch (e) {
      devLog("SecureStorage.delete error", e);
    }
  }

  async hasCredentials(connId: string): Promise<boolean> {
    return (await this.getCredentials(connId)) != null;
  }
}

export const secureStorageService: ISecureStorageService = new SecureStorageService();
