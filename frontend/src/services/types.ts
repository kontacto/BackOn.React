// Contratos (interfaces) dos serviços de autenticação/biometria.
// Mantém baixo acoplamento: as telas dependem destas abstrações, não da implementação.

export type AuthCredentials = {
  usuario: string;
  senha: string;
};

export type BiometricErrorCode =
  | "unavailable" // hardware ausente
  | "not_enrolled" // sem biometria cadastrada no aparelho
  | "cancelled" // usuário cancelou
  | "failed" // falha de leitura
  | "unknown";

export type BiometricSupport = {
  hasHardware: boolean;
  isEnrolled: boolean;
  supported: boolean; // hasHardware && isEnrolled
};

export type BiometricResult = {
  success: boolean;
  error?: BiometricErrorCode;
};

export type AuthLoginResult = {
  success: boolean;
  message: string;
  // Dados crus retornados pelo backend (sessão é montada na camada de UI).
  data?: Record<string, unknown> | null;
  httpOk: boolean;
};

export interface ISecureStorageService {
  saveCredentials(connId: string, creds: AuthCredentials): Promise<void>;
  getCredentials(connId: string): Promise<AuthCredentials | null>;
  deleteCredentials(connId: string): Promise<void>;
  hasCredentials(connId: string): Promise<boolean>;
}

export interface IBiometricService {
  getSupport(): Promise<BiometricSupport>;
  authenticate(reason?: string): Promise<BiometricResult>;
}

export type LoginConnection = {
  empresa: string;
  servidor: string;
  banco: string;
  api: string;
};

export interface IAuthService {
  login(conn: LoginConnection, creds: AuthCredentials): Promise<AuthLoginResult>;
}

// Identificador estável da credencial: conexão (empresa + banco).
export function connId(empresa: string, banco: string): string {
  return `${(empresa || "").trim()}__${(banco || "").trim()}`;
}
