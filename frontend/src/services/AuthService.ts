// Centraliza a autenticação por usuário/senha contra o backend (POST /api/login).
// Reutilizado tanto pelo login tradicional quanto pelo login biométrico.
import { AuthCredentials, AuthLoginResult, IAuthService, LoginConnection } from "./types";
import { devLog } from "./logger";

const GENERIC_AUTH_ERROR = "Usuário ou senha inválidos.";

function normalizeApiUrl(url: string): string {
  return (url || "").trim().replace(/\/+$/, "");
}

class AuthService implements IAuthService {
  async login(conn: LoginConnection, creds: AuthCredentials): Promise<AuthLoginResult> {
    const apiUrl = normalizeApiUrl(conn.api);
    if (!apiUrl) {
      return { success: false, message: "Conexão sem URL da API.", httpOk: false };
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const resp = await fetch(`${apiUrl}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          empresa: conn.empresa,
          servidor: conn.servidor,
          banco: conn.banco,
          usuario: creds.usuario.trim(),
          senha: creds.senha,
        }),
        signal: controller.signal,
      });
      const data = (await resp.json()) as (Record<string, unknown> & { detail?: string; success?: boolean; message?: string });
      if (!resp.ok) {
        return { success: false, message: (data?.detail as string) || GENERIC_AUTH_ERROR, httpOk: false, data };
      }
      return {
        success: !!data?.success,
        message: (data?.message as string) || (data?.success ? "OK" : GENERIC_AUTH_ERROR),
        httpOk: true,
        data,
      };
    } catch (e) {
      devLog("AuthService.login error", e);
      return { success: false, message: "Falha de conexão com o servidor.", httpOk: false };
    } finally {
      clearTimeout(timer);
    }
  }
}

export const authService: IAuthService = new AuthService();
export { GENERIC_AUTH_ERROR };
