// Abstração da biometria do dispositivo (impressão digital / Face ID) via expo-local-authentication.
import * as LocalAuthentication from "expo-local-authentication";

import { BiometricResult, BiometricSupport, IBiometricService } from "./types";
import { devLog } from "./logger";

class BiometricService implements IBiometricService {
  async getSupport(): Promise<BiometricSupport> {
    try {
      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const isEnrolled = await LocalAuthentication.isEnrolledAsync();
      return { hasHardware, isEnrolled, supported: hasHardware && isEnrolled };
    } catch (e) {
      devLog("Biometric.getSupport error", e);
      return { hasHardware: false, isEnrolled: false, supported: false };
    }
  }

  async authenticate(reason = "Confirme sua identidade"): Promise<BiometricResult> {
    try {
      const support = await this.getSupport();
      if (!support.hasHardware) return { success: false, error: "unavailable" };
      if (!support.isEnrolled) return { success: false, error: "not_enrolled" };

      const res = await LocalAuthentication.authenticateAsync({
        promptMessage: reason,
        cancelLabel: "Cancelar",
        disableDeviceFallback: false,
      });
      if (res.success) return { success: true };

      // Mapeia o motivo da falha sem expor detalhes técnicos ao usuário.
      const err = (res as { error?: string }).error || "";
      devLog("Biometric.authenticate fail", err);
      if (err === "user_cancel" || err === "system_cancel" || err === "app_cancel") {
        return { success: false, error: "cancelled" };
      }
      return { success: false, error: "failed" };
    } catch (e) {
      devLog("Biometric.authenticate error", e);
      return { success: false, error: "unknown" };
    }
  }
}

export const biometricService: IBiometricService = new BiometricService();
