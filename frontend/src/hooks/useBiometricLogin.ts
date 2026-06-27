// Orquestra o login biométrico: disponibilidade, ativação, autenticação e desativação.
// Nenhuma lógica fica na tela — apenas consome este hook (Separation of Concerns).
import { useCallback, useEffect, useState } from "react";

import { authService } from "@/src/services/AuthService";
import { biometricService } from "@/src/services/BiometricService";
import { secureStorageService } from "@/src/services/SecureStorageService";
import {
  AuthCredentials, BiometricErrorCode, BiometricSupport, LoginConnection, connId,
} from "@/src/services/types";

export type BioConnection = LoginConnection & { permitirBiometria?: boolean };

// Mensagens amigáveis (sem detalhes técnicos) por código de erro.
const FRIENDLY: Record<BiometricErrorCode, string | null> = {
  unavailable: "Este aparelho não possui biometria.",
  not_enrolled: "Nenhuma biometria está cadastrada neste aparelho.",
  cancelled: null, // silencioso quando o usuário cancela
  failed: "Não foi possível ler sua biometria. Tente novamente.",
  unknown: "Não foi possível usar a biometria agora.",
};

export function biometricErrorMessage(code?: BiometricErrorCode): string | null {
  return code ? FRIENDLY[code] : null;
}

export function useBiometricLogin(selected: BioConnection | null) {
  const [support, setSupport] = useState<BiometricSupport | null>(null);
  const [hasStored, setHasStored] = useState(false);
  const enabledByConfig = !!selected?.permitirBiometria;
  const id = selected ? connId(selected.empresa, selected.banco) : "";

  const refresh = useCallback(async () => {
    if (!selected || !enabledByConfig) {
      setSupport(null);
      setHasStored(false);
      return;
    }
    const sup = await biometricService.getSupport();
    setSupport(sup);
    setHasStored(await secureStorageService.hasCredentials(id));
  }, [selected, enabledByConfig, id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Mostra o botão "Entrar com Biometria" só quando todas as condições batem.
  const canBiometricLogin = enabledByConfig && !!support?.supported && hasStored;

  // Após login por senha: oferecer ativação? (config + suporte + ainda não ativado)
  const shouldOfferEnable = enabledByConfig && !!support?.supported && !hasStored;

  // Autentica via biometria e refaz o login no backend com as credenciais salvas.
  const loginWithBiometrics = useCallback(async (): Promise<{
    ok: boolean; data?: Record<string, unknown> | null; message?: string | null;
  }> => {
    if (!selected) return { ok: false, message: "Selecione uma empresa." };
    const bio = await biometricService.authenticate("Entrar com biometria");
    if (!bio.success) return { ok: false, message: biometricErrorMessage(bio.error) };
    const creds = await secureStorageService.getCredentials(id);
    if (!creds) return { ok: false, message: "Faça login com usuário e senha." };
    const res = await authService.login(selected, creds);
    if (!res.success) {
      // Credenciais inválidas / token expirado → limpa para forçar login tradicional.
      if (res.httpOk) await secureStorageService.deleteCredentials(id);
      await refresh();
      return { ok: false, data: res.data, message: "Sessão expirada. Entre com usuário e senha." };
    }
    return { ok: true, data: res.data };
  }, [selected, id, refresh]);

  // Ativa: valida biometria e grava credenciais com segurança.
  const enableBiometrics = useCallback(async (creds: AuthCredentials): Promise<{ ok: boolean; message?: string | null }> => {
    const bio = await biometricService.authenticate("Confirme para habilitar a biometria");
    if (!bio.success) return { ok: false, message: biometricErrorMessage(bio.error) };
    await secureStorageService.saveCredentials(id, creds);
    setHasStored(true);
    return { ok: true };
  }, [id]);

  const disableBiometrics = useCallback(async () => {
    await secureStorageService.deleteCredentials(id);
    setHasStored(false);
  }, [id]);

  return {
    support, hasStored, enabledByConfig,
    canBiometricLogin, shouldOfferEnable,
    loginWithBiometrics, enableBiometrics, disableBiometrics, refresh,
  };
}
